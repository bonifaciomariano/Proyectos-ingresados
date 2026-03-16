# =============================================================================
#  GENERADOR DE REPORTE SEMANAL — Prosecretaría Parlamentaria
#  Senado de la Nación Argentina
# =============================================================================
#
#  USO SEMANAL:
#  1. Reemplazá el valor de EXCEL_PROYECTOS con el nombre del nuevo archivo
#  2. Corré:  python generar_html.py
#  3. Subí el index.html generado a GitHub
#
# =============================================================================

# --- CONFIGURACIÓN (lo único que cambia cada semana) -------------------------

EXCEL_PROYECTOS  = "Ingresados_primera_quincena_marzo.xlsx"
EXCEL_SENADORES  = "Senadores_2026.xlsx"
TITULO_PERIODO   = "1.ª Quincena · Marzo 2026"
FECHA_DATOS      = "13/03/2026"
ARCHIVO_SALIDA   = "index.html"

# -----------------------------------------------------------------------------

import json, sys
try:
    import openpyxl
except ImportError:
    print("ERROR: falta la librería openpyxl.")
    print("Instalala con:  pip install openpyxl")
    sys.exit(1)

# ── 1. Cargar padrón de senadores → bloque ───────────────────────────────────

print(f"Leyendo senadores desde: {EXCEL_SENADORES}")
try:
    wb_sen = openpyxl.load_workbook(EXCEL_SENADORES)
except FileNotFoundError:
    print(f"ERROR: no se encontró el archivo '{EXCEL_SENADORES}'")
    sys.exit(1)

ws_sen = wb_sen.active
senador_bloque = {}
for row in ws_sen.iter_rows(min_row=2, values_only=True):
    bloque, apellido, nombre = row[0], row[1], row[2]
    if apellido and nombre:
        key = f"{apellido.strip()}, {nombre.strip()}".upper()
        senador_bloque[key] = bloque

print(f"  → {len(senador_bloque)} senadores cargados")

# ── 2. Cargar proyectos ───────────────────────────────────────────────────────

print(f"Leyendo proyectos desde: {EXCEL_PROYECTOS}")
try:
    wb_proy = openpyxl.load_workbook(EXCEL_PROYECTOS)
except FileNotFoundError:
    print(f"ERROR: no se encontró el archivo '{EXCEL_PROYECTOS}'")
    sys.exit(1)

ws_proy = wb_proy.active
headers = [cell.value for cell in ws_proy[1]]

# Extraer hipervínculos de columna NRO. (índice 1)
nro_links = {}
for row in ws_proy.iter_rows(min_row=2):
    cell = row[1]
    if cell.value and cell.hyperlink:
        url = cell.hyperlink.target if hasattr(cell.hyperlink, "target") else str(cell.hyperlink)
        nro_links[int(cell.value)] = url

TIPOS = {
    "PL": "Proyecto de Ley",
    "PD": "Proyecto de Declaración",
    "PC": "Proyecto de Comunicación",
    "PR": "Proyecto de Resolución",
    "CA": "Comunicación Aprobada",
    "AC": "Acuerdo",
    "CV": "Convenio",
}

def parse_autores(s):
    if not s:
        return []
    return [p.strip().rstrip("-").strip() for p in s.split(" - ") if p.strip().rstrip("-").strip()]

def get_bloques(autores):
    seen, result = set(), []
    for a in autores:
        b = senador_bloque.get(a.upper(), "Sin datos")
        if b not in seen:
            seen.add(b)
            result.append(b)
    return result

def extract_extracto(caratula):
    if ":" in caratula:
        return caratula[caratula.index(":") + 1:].strip()
    return caratula.strip()

proyectos = []
for row in ws_proy.iter_rows(min_row=2, values_only=True):
    r = dict(zip(headers, row))
    if not any(v for v in row):
        continue
    autores    = parse_autores(r.get("AUTOR", ""))
    bloques    = get_bloques(autores)
    comisiones = [r.get(f"COMISION{i}") for i in range(1, 4) if r.get(f"COMISION{i}")]
    mesa       = r.get("MESA DE ENTRADAS", "") or ""
    fecha      = mesa.split(" -")[0].strip() if mesa else ""
    caratula   = r.get("CARÁTULA", "") or ""
    extracto   = extract_extracto(caratula)
    nro        = int(r["NRO."]) if r.get("NRO.") else 0
    origen     = r.get("ORIGEN", "S") or "S"

    proyectos.append({
        "nro":        nro,
        "anio":       int(r["AÑO"]) if r.get("AÑO") else 2026,
        "tipo":       r.get("TIPO", ""),
        "tipo_label": TIPOS.get(r.get("TIPO", ""), r.get("TIPO", "")),
        "extracto":   extracto,
        "autores":    autores,
        "bloques":    bloques,
        "comisiones": comisiones,
        "fecha":      fecha,
        "dae":        r.get("NRO. DAE / DADO CUENTA", "") or "",
        "origen":     origen,
        "url":        nro_links.get(nro, ""),
    })

proyectos.sort(key=lambda x: x["nro"], reverse=True)
total = len(proyectos)
print(f"  → {total} proyectos procesados")
print(f"  → {sum(1 for p in proyectos if p['url'])} con hipervínculo")

datos_js = json.dumps(proyectos, ensure_ascii=False)

# ── 3. Construir HTML ─────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Poppins',Calibri,sans-serif;background:#E8EEF5;color:#4A4A4A;font-size:15px;line-height:1.5}
.header{background:#1B5EA2;padding:14px 16px;position:sticky;top:0;z-index:100;border-bottom:2px solid #0d3f73}
.header-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.header-inst{font-size:9px;font-weight:400;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:2px}
.header-dep{font-size:9px;font-weight:700;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:2px}
.header-title{font-size:18px;font-weight:700;color:#fff}
.header-subtitle{font-size:12px;color:rgba(255,255,255,0.8);margin-top:1px}
.section-block{background:#fff;margin:12px;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08)}
.section-header{background:#1B5EA2;padding:10px 16px;display:flex;justify-content:space-between;align-items:center}
.section-header h2{font-size:11px;font-weight:700;color:#fff;text-transform:uppercase;letter-spacing:1.5px}
.section-hint{font-size:10px;color:rgba(255,255,255,0.65)}
.section-body{padding:16px}
.stat-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-bottom:16px}
.stat-card{background:#F5F7FA;border-radius:8px;padding:14px 12px;border-left:4px solid #1B5EA2}
.stat-num{font-size:30px;font-weight:700;color:#1B5EA2;line-height:1}
.stat-label{font-size:12px;color:#4A4A4A;margin-top:3px}
.dash-subtitle{font-size:11px;font-weight:600;color:#2E75B6;text-transform:uppercase;letter-spacing:1px;margin:14px 0 8px;padding-bottom:4px;border-bottom:1px solid #D6E4F0}
.tipo-bar-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;cursor:pointer;padding:4px 6px;border-radius:6px;transition:background .12s}
.tipo-bar-row:hover{background:#F0F4FA}
.tipo-bar-row.on{background:#D6E4F0}
.tipo-pill{font-size:11px;font-weight:700;border-radius:4px;padding:3px 8px;min-width:36px;text-align:center;flex-shrink:0}
.tipo-nombre{font-size:13px;color:#4A4A4A;flex:1}
.bar-track{flex:2;height:7px;background:#D6E4F0;border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:width .3s}
.tipo-count{font-size:13px;font-weight:700;min-width:28px;text-align:right}
.bloque-row{display:flex;align-items:center;gap:8px;margin-bottom:7px;cursor:pointer;padding:3px 6px;border-radius:6px;transition:background .12s}
.bloque-row:hover,.com-row:hover{background:#F0F4FA}
.bloque-row.on,.com-row.on{background:#D6E4F0}
.bloque-name{font-size:12px;color:#4A4A4A;flex:1;line-height:1.3}
.bloque-bar-track{width:80px;height:6px;background:#D6E4F0;border-radius:3px;overflow:hidden;flex-shrink:0}
.bloque-bar-fill{height:100%;border-radius:3px;transition:width .3s}
.bloque-count{font-size:12px;font-weight:700;color:#2E75B6;min-width:26px;text-align:right}
.com-row{display:flex;align-items:center;gap:8px;margin-bottom:7px;cursor:pointer;padding:3px 6px;border-radius:6px;transition:background .12s}
.com-name{font-size:12px;color:#4A4A4A;flex:1;line-height:1.3}
.com-bar-track{width:80px;height:6px;background:#D6E4F0;border-radius:3px;overflow:hidden;flex-shrink:0}
.com-bar-fill{height:100%;background:#2E75B6;border-radius:3px;transition:width .3s}
.com-count{font-size:12px;font-weight:700;color:#2E75B6;min-width:26px;text-align:right}
.dash-context{font-size:11px;color:#2E75B6;background:#EAF0FA;border-radius:6px;padding:6px 10px;margin-bottom:10px;display:none}
.dash-context.visible{display:block}
.search-box{width:100%;padding:11px 14px;border:1.5px solid #D6E4F0;border-radius:8px;font-family:inherit;font-size:14px;color:#4A4A4A;outline:none;margin-bottom:12px;background:#fff}
.search-box:focus{border-color:#1B5EA2}
.filter-label{font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.filter-row{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:4px}
.chip{padding:7px 13px;border-radius:20px;border:1.5px solid #D6E4F0;background:#fff;font-family:inherit;font-size:12px;color:#4A4A4A;cursor:pointer;transition:all .15s;white-space:nowrap;-webkit-appearance:none;line-height:1.2}
.chip.on{background:#1B5EA2;border-color:#1B5EA2;color:#fff;font-weight:600}
.results-count{font-size:12px;color:#888;margin-top:10px}
.select-wrapper{position:relative;display:block;margin-bottom:4px}
.filter-select{width:100%;padding:9px 36px 9px 13px;border:1.5px solid #D6E4F0;border-radius:8px;font-family:inherit;font-size:13px;color:#4A4A4A;background:#fff;outline:none;cursor:pointer;-webkit-appearance:none;appearance:none;transition:border-color .15s}
.filter-select:focus,.filter-select.on{border-color:#1B5EA2;background:#EAF0FA;color:#1B5EA2;font-weight:600}
.select-arrow{position:absolute;right:11px;top:50%;transform:translateY(-50%);pointer-events:none;color:#888;font-size:13px}
.list-section{padding:0 12px 12px}
.card{background:#fff;border-radius:10px;margin-bottom:10px;overflow:hidden;border:1px solid #D6E4F0;box-shadow:0 1px 3px rgba(0,0,0,0.05)}
.card-exp{display:flex;align-items:center;justify-content:space-between;padding:9px 14px 7px;border-bottom:1px solid #EEF2F8;background:#F5F8FC}
.exp-id{display:flex;align-items:center;gap:8px}
.exp-badge{font-size:11px;font-weight:700;padding:4px 9px;border-radius:4px;flex-shrink:0;letter-spacing:.5px}
.exp-nro{font-size:14px;font-weight:700;color:#1B5EA2}
.exp-link{font-size:11px;color:#2E75B6;text-decoration:none;font-weight:600;border:1px solid #2E75B6;padding:3px 9px;border-radius:12px;white-space:nowrap;transition:all .15s}
.exp-link:hover{background:#2E75B6;color:#fff}
.exp-fecha{font-size:11px;color:#888}
.card-body{padding:12px 14px 6px}
.extracto{font-size:14px;font-weight:600;color:#2C2C2C;line-height:1.4;margin-bottom:10px}
.card-meta{display:flex;flex-direction:column;gap:5px;padding-bottom:10px}
.meta-row{display:flex;gap:6px;align-items:flex-start;flex-wrap:wrap}
.meta-bold{font-size:13px;font-weight:600;color:#4A4A4A}
.btag{display:inline-block;font-size:11px;font-weight:600;padding:3px 8px;border-radius:4px;margin-right:4px;margin-bottom:3px}
.ctag{display:inline-block;font-size:11px;padding:3px 8px;border-radius:4px;margin-right:4px;margin-bottom:3px;background:#EAF0FA;color:#1B5EA2;border:1px solid #c8daf0}
.no-results{text-align:center;padding:48px 16px;color:#aaa;font-size:14px}
.footer{text-align:center;padding:20px 16px;font-size:11px;color:#aaa;font-style:italic}
"""

JS = r"""
var TIPOS = {PL:'Proy. de Ley',PD:'Declaraci\u00f3n',PC:'Comunicaci\u00f3n',PR:'Resoluci\u00f3n',CA:'Com. Aprobada',AC:'Acuerdo',CV:'Convenio'};
var TIPO_FG = {PL:'#1B5EA2',PD:'#2E75B6',PC:'#0d7a4a',PR:'#5B4DA0',CA:'#1a7a4a',AC:'#7a5c1a',CV:'#7a1a3a'};
var TIPO_BG = {PL:'#D6E4F0',PD:'#EAF0FA',PC:'#DCF0E8',PR:'#EDE8FA',CA:'#E0F4EC',AC:'#F9F0DA',CV:'#FAE0EA'};
var BC = ['#1B5EA2','#2E75B6','#5B4DA0','#1a7a4a','#7a5c1a','#7a1a3a','#2E8B7A','#6B3A2A','#1a4a7a','#4a7a1a','#7a1a5a','#2a7a6a','#5a2a7a','#2a5a2a'];
var ALL_BLOQUES = [];
var dashFiltroTipo = '', dashFiltroBloque = '', dashFiltroCom = '';
var activeTipos = {}, activeBloques = {}, activeOrigen = '';

function init(){
  var bset = {};
  DATA.forEach(function(p){ p.bloques.forEach(function(b){ bset[b]=1; }); });
  ALL_BLOQUES = Object.keys(bset).sort();

  var cset = {};
  DATA.forEach(function(p){ p.comisiones.forEach(function(c){ cset[c]=1; }); });
  var coms = Object.keys(cset).sort();
  var cSel = document.getElementById('com-select');
  coms.forEach(function(c){
    var opt = document.createElement('option');
    opt.value = c; opt.textContent = c; cSel.appendChild(opt);
  });

  var aset = {};
  DATA.forEach(function(p){ p.autores.forEach(function(a){ aset[a]=1; }); });
  var autores = Object.keys(aset).sort();
  var aSel = document.getElementById('autor-select');
  autores.forEach(function(a){
    var opt = document.createElement('option');
    opt.value = a; opt.textContent = a; aSel.appendChild(opt);
  });

  renderDash(DATA);
  renderFilters();
  renderList();
}

function getBloqueColor(b){
  return BC[ALL_BLOQUES.indexOf(b) % BC.length];
}

function getDashFiltered(){
  return DATA.filter(function(p){
    if(dashFiltroTipo && p.tipo !== dashFiltroTipo) return false;
    if(dashFiltroBloque && p.bloques.indexOf(dashFiltroBloque) < 0) return false;
    if(dashFiltroCom && p.comisiones.indexOf(dashFiltroCom) < 0) return false;
    return true;
  });
}

function calcStats(data){
  var tipos={}, bloques={}, coms={};
  data.forEach(function(p){
    tipos[p.tipo] = (tipos[p.tipo]||0)+1;
    p.bloques.forEach(function(b){ bloques[b]=(bloques[b]||0)+1; });
    p.comisiones.forEach(function(c){ coms[c]=(coms[c]||0)+1; });
  });
  return {tipos:tipos, bloques:bloques, coms:coms};
}

function renderDash(data){
  var s = calcStats(data);
  var total = data.length;
  document.getElementById('stat-total').innerHTML = total;
  document.getElementById('stat-pl').innerHTML = s.tipos['PL']||0;
  document.getElementById('stat-pd').innerHTML = s.tipos['PD']||0;
  document.getElementById('stat-otros').innerHTML = total - (s.tipos['PL']||0) - (s.tipos['PD']||0);

  var partes = [];
  if(dashFiltroTipo) partes.push('Tipo: '+(TIPOS[dashFiltroTipo]||dashFiltroTipo));
  if(dashFiltroBloque) partes.push('Bloque: '+dashFiltroBloque);
  if(dashFiltroCom) partes.push('Comisi\u00f3n: '+dashFiltroCom);
  var ctx = document.getElementById('dash-context');
  if(partes.length){
    ctx.innerHTML = 'Filtrando por: <strong>'+partes.join(' &middot; ')+'</strong> &nbsp;<button onclick="clearDash()" style="background:none;border:none;color:#1B5EA2;cursor:pointer;font-size:11px;font-weight:700;padding:0 4px">&#x2715; Limpiar</button>';
    ctx.className = 'dash-context visible';
  } else { ctx.className = 'dash-context'; }

  var tipoOrder = ['PL','PD','PC','PR','CA','AC','CV'];
  var maxT = 0;
  tipoOrder.forEach(function(t){ if((s.tipos[t]||0)>maxT) maxT=s.tipos[t]||0; });
  var tbars = '';
  tipoOrder.forEach(function(t){
    if(!DATA.some(function(p){return p.tipo===t;})) return;
    var n = s.tipos[t]||0, pct = maxT ? Math.round(n/maxT*100) : 0;
    var fg = TIPO_FG[t]||'#888', bg = TIPO_BG[t]||'#eee';
    var on = dashFiltroTipo===t ? ' on' : '';
    tbars += '<div class="tipo-bar-row'+on+'" onclick="clickDashTipo(\''+t+'\')">'+
      '<span class="tipo-pill" style="background:'+bg+';color:'+fg+'">'+t+'</span>'+
      '<span class="tipo-nombre">'+(TIPOS[t]||t)+'</span>'+
      '<div class="bar-track"><div class="bar-fill" style="width:'+pct+'%;background:'+fg+'"></div></div>'+
      '<span class="tipo-count" style="color:'+fg+'">'+n+'</span></div>';
  });
  document.getElementById('tipo-bars').innerHTML = tbars;

  var blist = Object.keys(s.bloques).sort(function(a,b){ return s.bloques[b]-s.bloques[a]; });
  var maxB = blist.length ? s.bloques[blist[0]] : 1;
  var bbars = '';
  blist.forEach(function(b){
    var n = s.bloques[b], pct = Math.round(n/maxB*100);
    var color = getBloqueColor(b);
    var safe = b.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
    var on = dashFiltroBloque===b ? ' on' : '';
    bbars += '<div class="bloque-row'+on+'" onclick="clickDashBloque(\''+safe+'\')">'+
      '<span class="bloque-name">'+b+'</span>'+
      '<div class="bloque-bar-track"><div class="bloque-bar-fill" style="width:'+pct+'%;background:'+color+'"></div></div>'+
      '<span class="bloque-count">'+n+'</span></div>';
  });
  document.getElementById('bloque-bars').innerHTML = bbars;

  var clist = Object.keys(s.coms).sort(function(a,b){ return s.coms[b]-s.coms[a]; }).slice(0,8);
  var maxC = clist.length ? s.coms[clist[0]] : 1;
  var cbars = '';
  clist.forEach(function(c){
    var n = s.coms[c], pct = Math.round(n/maxC*100);
    var safe = c.replace(/\\/g,'\\\\').replace(/'/g,"\\'");
    var on = dashFiltroCom===c ? ' on' : '';
    cbars += '<div class="com-row'+on+'" onclick="clickDashCom(\''+safe+'\')">'+
      '<span class="com-name">'+c+'</span>'+
      '<div class="com-bar-track"><div class="com-bar-fill" style="width:'+pct+'%"></div></div>'+
      '<span class="com-count">'+n+'</span></div>';
  });
  document.getElementById('com-bars').innerHTML = cbars;
}

function clickDashTipo(t){ dashFiltroTipo = dashFiltroTipo===t?'':t; renderDash(getDashFiltered()); }
function clickDashBloque(b){ dashFiltroBloque = dashFiltroBloque===b?'':b; renderDash(getDashFiltered()); }
function clickDashCom(c){ dashFiltroCom = dashFiltroCom===c?'':c; renderDash(getDashFiltered()); }
function clearDash(){ dashFiltroTipo=''; dashFiltroBloque=''; dashFiltroCom=''; renderDash(DATA); }

function renderFilters(){
  var tset = {};
  DATA.forEach(function(p){ tset[p.tipo]=1; });
  var tiposUsed = Object.keys(tset).sort();
  var anyTipo = Object.keys(activeTipos).length===0;
  var html = '<button class="chip'+(anyTipo?' on':'')+'" onclick="toggleTipo(\'__all__\')">Todos</button>';
  tiposUsed.forEach(function(t){
    html += '<button class="chip'+(activeTipos[t]?' on':'')+'" onclick="toggleTipo(\''+t+'\')">'+t+' &middot; '+(TIPOS[t]||t)+'</button>';
  });
  document.getElementById('tipo-filters').innerHTML = html;

  var anyBloque = Object.keys(activeBloques).length===0;
  var bhtml = '<button class="chip'+(anyBloque?' on':'')+'" onclick="toggleBloque(\'__all__\')">Todos</button>';
  ALL_BLOQUES.forEach(function(b){
    var safe = b.replace(/'/g,"\\'");
    bhtml += '<button class="chip'+(activeBloques[b]?' on':'')+'" onclick="toggleBloque(\''+safe+'\')">'+b+'</button>';
  });
  document.getElementById('bloque-filters').innerHTML = bhtml;

  var ORIGEN_LABEL = {S:'Senado', PE:'Poder Ejecutivo', OV:'Otros'};
  var ohtml = '<button class="chip'+(activeOrigen===''?' on':'')+'" onclick="toggleOrigen(\'\')">Todos</button>';
  ['S','PE','OV'].forEach(function(o){
    var isOn = activeOrigen===o;
    var peStyle = o==='PE' ? (isOn ? ' style="background:#4a0a22;border-color:#4a0a22;color:#fff;font-weight:700"' : ' style="background:#7a1a3a;border-color:#7a1a3a;color:#fff;font-weight:700"') : '';
    ohtml += '<button class="chip'+(isOn?' on':'')+'"'+peStyle+' onclick="toggleOrigen(\''+o+'\')">'+( ORIGEN_LABEL[o]||o)+'</button>';
  });
  document.getElementById('origen-filters').innerHTML = ohtml;
}

function toggleTipo(t){
  if(t==='__all__'){ activeTipos={}; } else { if(activeTipos[t]) delete activeTipos[t]; else activeTipos[t]=1; }
  renderFilters(); renderList();
}
function toggleBloque(b){
  if(b==='__all__'){ activeBloques={}; } else { if(activeBloques[b]) delete activeBloques[b]; else activeBloques[b]=1; }
  renderFilters(); renderList();
}
function toggleOrigen(o){
  activeOrigen = activeOrigen===o ? '' : o;
  renderFilters(); renderList();
}

function getFiltered(){
  var q = document.getElementById('search').value.toLowerCase().trim();
  var selCom = document.getElementById('com-select').value;
  var selAutor = document.getElementById('autor-select').value;
  return DATA.filter(function(p){
    if(Object.keys(activeTipos).length && !activeTipos[p.tipo]) return false;
    if(Object.keys(activeBloques).length){
      var match = false;
      p.bloques.forEach(function(b){ if(activeBloques[b]) match=true; });
      if(!match) return false;
    }
    if(activeOrigen && p.origen !== activeOrigen) return false;
    if(selCom && p.comisiones.indexOf(selCom) < 0) return false;
    if(selAutor && p.autores.indexOf(selAutor) < 0) return false;
    if(q){
      var hay = (p.extracto+' '+p.autores.join(' ')+' '+p.comisiones.join(' ')).toLowerCase();
      if(hay.indexOf(q)<0) return false;
    }
    return true;
  });
}

function renderList(){
  var filtered = getFiltered();
  var tot = filtered.length;
  document.getElementById('results-count').innerHTML = tot+' proyecto'+(tot!==1?'s':'')+' encontrado'+(tot!==1?'s':'');
  if(!filtered.length){
    document.getElementById('list').innerHTML = '<div class="no-results">Sin resultados para este filtro.</div>';
    return;
  }
  var html = '';
  filtered.forEach(function(p){
    var fg = TIPO_FG[p.tipo]||'#888', bg = TIPO_BG[p.tipo]||'#eee';
    var autoresTxt = p.autores.slice(0,3).join(' \u00b7 ')+(p.autores.length>3?' +'+(p.autores.length-3)+' m\u00e1s':'');
    var btags = '', ctags = '';
    p.bloques.forEach(function(b){
      var c = getBloqueColor(b);
      btags += '<span class="btag" style="background:'+c+'22;color:'+c+'">'+b+'</span>';
    });
    p.comisiones.forEach(function(c){ ctags += '<span class="ctag">'+c+'</span>'; });
    var expNro = p.origen+'-'+p.nro+'/'+p.anio;
    var dae = (p.dae && p.dae!=='-') ? ' &middot; DAE '+p.dae : '';
    var linkBtn = p.url ? '<a class="exp-link" href="'+p.url+'" target="_blank">Ver expediente &#8599;</a>' : '';
    html += '<div class="card">'+
      '<div class="card-exp">'+
        '<div class="exp-id">'+
          '<span class="exp-badge" style="background:'+bg+';color:'+fg+'">'+p.tipo+'</span>'+
          '<span class="exp-nro">'+expNro+'</span>'+
          (p.fecha ? '<span class="exp-fecha">'+p.fecha+'</span>' : '')+
        '</div>'+linkBtn+
      '</div>'+
      '<div class="card-body">'+
        '<div class="extracto">'+p.extracto+'</div>'+
        '<div class="card-meta">'+
          (autoresTxt ? '<div class="meta-row"><span class="meta-bold">'+autoresTxt+'</span></div>' : '')+
          (btags ? '<div class="meta-row">'+btags+'</div>' : '')+
          (ctags ? '<div class="meta-row">'+ctags+'</div>' : '')+
        '</div>'+
      '</div>'+
    '</div>';
  });
  document.getElementById('list').innerHTML = html;
}
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Proyectos Ingresados — {titulo}</title>
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>

<div class="header">
  <div class="header-row">
    <span class="header-inst">Senado de la Naci&oacute;n Argentina</span>
    <span class="header-dep">Prosecretar&iacute;a Parlamentaria</span>
  </div>
  <div class="header-title">Proyectos Ingresados</div>
  <div class="header-subtitle">{titulo}</div>
</div>

<div class="section-block">
  <div class="section-header">
    <h2>Dashboard</h2>
    <span class="section-hint">Toca para filtrar</span>
  </div>
  <div class="section-body">
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-num" id="stat-total">{total}</div>
        <div class="stat-label">Total proyectos</div>
      </div>
      <div class="stat-card" style="border-left-color:#2E75B6">
        <div class="stat-num" style="color:#2E75B6" id="stat-pl">{pl}</div>
        <div class="stat-label">Proyectos de ley</div>
      </div>
      <div class="stat-card" style="border-left-color:#5B4DA0">
        <div class="stat-num" style="color:#5B4DA0" id="stat-pd">{pd}</div>
        <div class="stat-label">Declaraciones</div>
      </div>
      <div class="stat-card" style="border-left-color:#1a7a4a">
        <div class="stat-num" style="color:#1a7a4a" id="stat-otros">{otros}</div>
        <div class="stat-label">Otros tipos</div>
      </div>
    </div>
    <div id="dash-context" class="dash-context"></div>
    <div class="dash-subtitle">Por tipo de proyecto</div>
    <div id="tipo-bars"></div>
    <div class="dash-subtitle">Por bloque pol&iacute;tico</div>
    <div id="bloque-bars"></div>
    <div class="dash-subtitle">Por comisiones</div>
    <div id="com-bars"></div>
  </div>
</div>

<div class="section-block">
  <div class="section-header">
    <h2>B&uacute;squeda y filtros</h2>
  </div>
  <div class="section-body">
    <input class="search-box" type="text" id="search" placeholder="Buscar por extracto, autor o comisi&oacute;n&hellip;" oninput="renderList()">
    <div class="filter-label">Tipo</div>
    <div class="filter-row" id="tipo-filters"></div>
    <div class="filter-label" style="margin-top:12px">Bloque</div>
    <div class="filter-row" id="bloque-filters"></div>
    <div class="filter-label" style="margin-top:12px">Origen</div>
    <div class="filter-row" id="origen-filters"></div>
    <div class="filter-label" style="margin-top:12px">Comisi&oacute;n</div>
    <div class="select-wrapper">
      <select class="filter-select" id="com-select" onchange="renderList()">
        <option value="">Todas las comisiones</option>
      </select>
      <span class="select-arrow">&#9660;</span>
    </div>
    <div class="filter-label" style="margin-top:12px">Autor</div>
    <div class="select-wrapper">
      <select class="filter-select" id="autor-select" onchange="renderList()">
        <option value="">Todos los autores</option>
      </select>
      <span class="select-arrow">&#9660;</span>
    </div>
    <div class="results-count" id="results-count"></div>
  </div>
</div>

<div class="section-block" style="overflow:visible;background:transparent;box-shadow:none">
  <div class="section-header" style="border-radius:10px 10px 0 0">
    <h2>Expedientes</h2>
  </div>
</div>
<div class="list-section" id="list"></div>

<div class="footer">Prosecretar&iacute;a Parlamentaria &middot; Senado de la Naci&oacute;n Argentina<br>Datos al {fecha}</div>

<script>
var DATA = {datos};
{js}
init();
</script>
</body>
</html>"""

# Calcular totales para el HTML estático inicial
tipos_count = {}
for p in proyectos:
    tipos_count[p["tipo"]] = tipos_count.get(p["tipo"], 0) + 1

html_final = HTML_TEMPLATE.format(
    titulo   = TITULO_PERIODO,
    fecha    = FECHA_DATOS,
    total    = total,
    pl       = tipos_count.get("PL", 0),
    pd       = tipos_count.get("PD", 0),
    otros    = total - tipos_count.get("PL", 0) - tipos_count.get("PD", 0),
    css      = CSS,
    datos    = datos_js,
    js       = JS,
)

with open(ARCHIVO_SALIDA, "w", encoding="utf-8") as f:
    f.write(html_final)

print(f"\nListo. Archivo generado: {ARCHIVO_SALIDA}  ({len(html_final):,} bytes)")
print(f"Subilo a GitHub y la URL se actualizará en 1-2 minutos.")

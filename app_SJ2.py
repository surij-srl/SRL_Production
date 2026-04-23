import streamlit as st
import os
import json
import glob
import pandas as pd
import plotly.express as px
from google import genai
from google.genai import types
import PIL.Image
from pdf2image import convert_from_path, convert_from_bytes
import simpy
import time

# --- 1. ALAPBEÁLLÍTÁSOK ---
st.set_page_config(page_title="AI Gyártásszimulátor", layout="wide")

# Mappák létrehozása
CACHE_MAPPA = "Technologiai_Kartyak"
if not os.path.exists(CACHE_MAPPA):
    os.makedirs(CACHE_MAPPA)

# AI Kliens beállítása
API_KEY = "AIzaSyDB_StuA-zOUneRmEygt4Gibst3M47SY0c" # <--- IDE ÍRD BE AZ API KULCSODAT!
client = genai.Client(api_key=API_KEY)

# --- 2. SEGÉDFÜGGVÉNYEK ---



def analyze_drawing(file):
    """Műhelyrajz elemzése AI-val (PDF/Kép támogatással)"""
    img = None
    try:
        # A file.name alapján döntünk a típusról
        file_extension = file.name.lower().split('.')[-1]
        
        if file_extension == "pdf":
            # PDF konvertálása memóriából
            # A file.read() beolvassa a bájtokat, a convert_from_bytes pedig feldolgozza
            pages = convert_from_bytes(file.read(), first_page=1, last_page=1)
            if pages:
                img = pages[0]
        elif file_extension in ["jpg", "jpeg", "png"]:
            img = PIL.Image.open(file)
        else:
            st.error(f"Nem támogatott fájlformátum: {file_extension}")
            return None

        if img is None:
            return None

        prompt = """
        Te egy tapasztalt gyártástervező mérnök vagy. 
        Elemezd a rajzot és adj választ JSON formátumban!
        Szerkezet:
        {
          "alkatresz_neve": "Példa alkatrész",
          "anyagigeny" [
            {"anyag": "Acél", "anyagminoseg": "1.2304", "mennyiseg": 10, "mertekegyseg": "kg"}
          ],
          "muveleti_sorrend": [
            {"lepes": 1, "gep": "Eszterga", "muvelet": "Nagyolás", "ido_perc": 15, "beallitasi_ido": 5, "kezelo_igeny": 1}
          ]
        }
        Fontos: Csak érvényes JSON-t adj vissza!
        """
        # --- ÚJRAPRÓBÁLKOZÁSI LOGIKA ---
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[prompt, img],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                return json.loads(response.text, strict=False)

            except Exception as e:
                # Ha 503-as hiba van és még van próbálkozási lehetőségünk
                if "503" in str(e) and attempt < max_retries - 1:
                    st.warning(f"Szerver túlterhelt, újrapróbálkozás {attempt+1}/{max_retries}...")
                    time.sleep(3) # Várunk 3 másodpercet
                    continue
                else:
                    # Ha minden próbálkozás elfogyott, vagy más hiba van
                    raise e

    except Exception as e:
        st.error(f"Hiba az elemzés során: {e}")
        return None

def get_stored_techs():
    """Összes mentett technológia beolvasása"""
    files = glob.glob(os.path.join(CACHE_MAPPA, "*.json"))
    techs = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as file:
                techs.append(json.load(file))
        except:
            pass
    return techs

# --- 3. SZIMULÁCIÓS MOTOR ---
def run_simulation(production_plan):
    env = simpy.Environment()
    machine_resources = {}
    results = []

    def part_process(name, ops):
        if not ops:
            print(f"⚠️ Hiba: {name} alkatrésznek nincsenek műveletei!")
            return

        for op in ops:
            gep = op.get('gep')
            if not gep: 
                continue
                
            if gep not in machine_resources:
                machine_resources[gep] = simpy.Resource(env, capacity=1)
            
            # Idő kinyerése és ellenőrzése
            try:
                ciklus_ido = float(op.get('ido_perc', 0) or 0)
                beall_ido = float(op.get('beallitasi_ido', 0) or 0)
                duration = ciklus_ido + beall_ido
            except (ValueError, TypeError):
                duration = 0.1 # Minimum idő, ha hibás az adat

            start_time = env.now
            with machine_resources[gep].request() as req:
                yield req
                yield env.timeout(duration)
                end_time = env.now
                
                results.append({
                    "Task": name, 
                    "Start": start_time, 
                    "Finish": end_time, 
                    "Resource": gep
                })
                print(f"✅ {name} - {gep} kész: {start_time} -> {end_time}")

    # Folyamatok indítása
    for item in production_plan:
        env.process(part_process(item['alkatresz_neve'], item['muveleti_sorrend']))
    
    env.run()
    
    # Debug: kiírjuk hány eredmény született
    print(f"📊 Szimuláció vége. Összesen {len(results)} művelet rögzítve.")
    return results



def part_process(name, ops):
    for op in ops:
        gep = op.get('gep', 'Ismeretlen gép')
        if gep not in machine_resources:
            machine_resources[gep] = simpy.Resource(env, capacity=1)
        
        start_time = env.now
        with machine_resources[gep].request() as req:
            yield req
            
            # BIZTONSÁGOS ÖSSZEADÁS: 
            # Ha az érték None, akkor 0-t használunk helyette
            ciklus_ido = op.get('ido_perc') if op.get('ido_perc') is not None else 0
            beall_ido = op.get('beallitasi_ido') if op.get('beallitasi_ido') is not None else 0
            
            duration = float(ciklus_ido) + float(beall_ido)
            
            # Ha véletlenül 0 lenne az idő, adjunk neki egy minimális értéket (vagy hagyjuk ki)
            if duration <= 0:
                duration = 0.1 
                
            yield env.timeout(duration)
            end_time = env.now
            results.append(dict(Task=name, Start=start_time, Finish=end_time, Resource=gep))


    for item in production_plan:
        env.process(part_process(item['alkatresz_neve'], item['muveleti_sorrend']))
    
    env.run()
    return results

# --- 4. FELHASZNÁLÓI FELÜLET (STREAMLIT) ---

st.sidebar.title("🏭 Gyártásvezérlő")
page = st.sidebar.radio("Menü", ["Új rajz beolvasása", "Technológia Adattár", "Szimuláció indítása"])

# --- ÚJ RAJZ BEOLVASÁSA OLDAL ---
if page == "Új rajz beolvasása":
    st.header("🔍 Új műhelyrajz elemzése")
    # Itt kapjuk meg a LISTÁT
    uploaded_files = st.file_uploader("Válassz fájlokat", type=['pdf', 'jpg', 'png'], accept_multiple_files=True)

    if uploaded_files:
        # Végigmegyünk a lista elemein egyesével
        for file in uploaded_files:
            # Egyedi azonosító a session_state számára fájlonként
            state_key = f"data_{file.name}"
            
            # Csak akkor elemezzük, ha még nincs a memóriában
            if state_key not in st.session_state:
                with st.spinner(f"Elemzés: {file.name}..."):
                    data = analyze_drawing(file) # Itt már a 'file' (egy elem) megy át, nem a lista!
                    if data:
                        st.session_state[state_key] = data

        # Megjelenítjük az összes beolvasott, de még nem mentett adatot
        for key in list(st.session_state.keys()):
            if key.startswith("data_"):
                data = st.session_state[key]
                with st.expander(f"📥 Mentésre vár: {data['alkatresz_neve']}", expanded=True):
                    # Szerkeszthető táblázat egyedi kulccsal
                    df_editor = st.data_editor(
                        pd.DataFrame(data['muveleti_sorrend']),
                        num_rows="dynamic",
                        key=f"editor_{key}"
                    )
                    
                    if st.button(f"💾 Mentés az Adattárba: {data['alkatresz_neve']}", key=f"save_btn_{key}"):
                        data['muveleti_sorrend'] = df_editor.to_dict('records')
                        
                        # Fájl mentése
                        safe_name = "".join([c for c in data['alkatresz_neve'] if c.isalnum() or c in (' ', '_')]).strip()
                        with open(os.path.join(CACHE_MAPPA, f"{safe_name}.json"), "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        
                        # Törlés a memóriából mentés után, hogy ne zavarjon
                        del st.session_state[key]
                        st.success("Sikeresen mentve!")
                        st.rerun()





# --- OLDAL: ADATTÁR ---
elif page == "Technológia Adattár":
    st.header("🗄️ Elmentett Technológiai Kártyák")
    all_tech = get_stored_techs()
    
    if not all_tech:
        st.info("Még nincsenek adatok.")
    else:
        for i, tech in enumerate(all_tech):
            with st.expander(f"📄 {tech['alkatresz_neve']}", key=f"exp_{i}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    # Szerkesztés az adattárban is
                    df_edit = st.data_editor(pd.DataFrame(tech['muveleti_sorrend']), num_rows="dynamic", key=f"ed_{i}")
                with col2:
                    if st.button("Update", key=f"up_{i}"):
                        tech['muveleti_sorrend'] = df_edit.to_dict('records')
                        # Újraírjuk a fájlt
                        safe_name = "".join([c for c in tech['alkatresz_neve'] if c.isalnum() or c in (' ', '_')]).strip()
                        with open(os.path.join(CACHE_MAPPA, f"{safe_name}.json"), "w", encoding="utf-8") as f:
                            json.dump(tech, f, ensure_ascii=False, indent=2)
                        st.rerun()
                    
                    if st.button("Törlés", key=f"del_{i}"):
                        safe_name = "".join([c for c in tech['alkatresz_neve'] if c.isalnum() or c in (' ', '_')]).strip()
                        os.remove(os.path.join(CACHE_MAPPA, f"{safe_name}.json"))
                        st.rerun()
# --- OLDAL: SZIMULÁCIÓ ---
elif page == "Szimuláció indítása":
    st.header("🚀 Gyártási Szimuláció")
    
    # 1. Betöltjük az aktuális kínálatot az adattárból
    all_techs = get_stored_techs()
    if not all_techs:
        st.warning("Nincsenek elmentett technológiák az adattárban! Előbb ments el egy rajzot.")
    else:
        tech_names = [t['alkatresz_neve'] for t in all_techs]
        selected = st.multiselect("Válaszd ki a gyártandó alkatrészeket:", tech_names)
        
        production_plan = []
        
        if selected:
            st.subheader("Gyártandó mennyiségek beállítása")
            # Segéd táblázat vagy inputok a mennyiséghez
            for name in selected:
                qty = st.number_input(f"Hány darabot gyártsunk: {name}?", min_value=1, value=1, key=f"sim_qty_{name}")
                
                # Megkeressük a technológiát a listában
                base_tech = next((t for t in all_techs if t['alkatresz_neve'] == name), None)

                
                if base_tech:
                    for j in range(qty):
                        # Mélymásolat készítése, hogy ne keveredjenek az adatok
                        item = json.loads(json.dumps(base_tech))
                        item['alkatresz_neve'] = f"{name} #{j+1}"
                        production_plan.append(item)
            
            st.divider()
            st.write(f"**Összesen {len(production_plan)} tétel kerül a szimulációba.**")

            # 2. INDÍTÁS GOMB
            if st.button("🚀 SZIMULÁCIÓ FUTTATÁSA"):
                if not production_plan:
                    st.error("Üres a gyártási terv!")
                else:
                    with st.spinner("Szimuláció számítása..."):
                        # Itt hívjuk meg a szimulációs motort
                        sim_results = run_simulation(production_plan)
                        
                        if sim_results:
                            st.success("Szimuláció kész!")
                            df_sim = pd.DataFrame(sim_results)
                            
                            # Gantt-diagram készítése
                            # Átalakítás dátumformátumra a Plotly miatt (perc alapú eltolás)
                            df_sim['Start_dt'] = pd.to_datetime(df_sim['Start'], unit='m', origin=pd.Timestamp('2024-01-01'))
                            df_sim['Finish_dt'] = pd.to_datetime(df_sim['Finish'], unit='m', origin=pd.Timestamp('2024-01-01'))
                            
                            fig = px.timeline(
                                df_sim, 
                                x_start="Start_dt", 
                                x_end="Finish_dt", 
                                y="Resource", 
                                color="Task",
                                hover_data=["Task"],
                                title="Gyártási Ütemterv (Gantt-diagram)"
                            )
                            
                            # Időtengely formázása, hogy perceket mutasson (ne dátumot)
                            fig.layout.xaxis.update({
                                'tickformat': '%H:%M',
                                'title': 'Idő (óra:perc)'
                            })
                            fig.update_yaxes(autorange="reversed")
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Statisztika megjelenítése
                            st.info(f"Teljes gyártási idő: {df_sim['Finish'].max()} perc")
                        else:
                            st.error("A szimuláció nem adott vissza eredményt. Ellenőrizd a technológiai adatokat!")

import streamlit as st
import folium
import streamlit.components.v1 as components
import pandas as pd
import itertools
import math
import colorsys
import json
import os
from ortools.linear_solver import pywraplp

# ==========================================
# 1. PAGE CONFIGURATION & INDESTRUCTIBLE CSS
# ==========================================
st.set_page_config(page_title="Truck Routing DSS", layout="wide")

st.markdown("""
<style>
    /* 1. THE EXTERNAL SCROLL-JUMP KILLER */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main, .block-container, .stHtml {
        overflow: hidden !important;
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        height: 100vh !important;
        width: 100vw !important;
    }
    
    /* 2. SOLID TOP NAVIGATION BAR */
    header[data-testid="stHeader"] { 
        background-color: #1e2129 !important; 
        height: 65px !important;
        border-bottom: 3px solid #4CAF50 !important;
        box-shadow: 0px 2px 10px rgba(0,0,0,0.5) !important;
        z-index: 999998 !important;
        pointer-events: auto !important; 
    }
    
    header[data-testid="stHeader"]::before {
        content: "🚛 Fleet Optimization Dashboard";
        position: absolute;
        top: 15px;
        left: 70px; 
        color: white;
        font-size: 22px;
        font-weight: 800;
        font-family: sans-serif;
        letter-spacing: 0.5px;
        white-space: nowrap;
        pointer-events: none;
    }
    
    /* Hide native decoration and top-level app toolbars */
    div[data-testid="stDecoration"], div[data-testid="stAppToolbar"], div[data-testid="stElementToolbar"] { 
        display: none !important; 
    }
    footer { display: none !important; }

    /* 3. SHIFT SIDEBAR TOGGLE DOWN TO CLEAR THE TOP BAR */
    [data-testid="collapsedControl"] {
        pointer-events: auto !important; 
        position: fixed !important;
        top: 80px !important; 
        left: 20px !important;
        background-color: #2b303b !important;
        border: 2px solid #4CAF50 !important;
        border-radius: 6px !important;
        padding: 6px !important;
        z-index: 9999999 !important;
        transition: all 0.2s ease !important;
    }
    [data-testid="collapsedControl"]:hover {
        background-color: #4CAF50 !important;
    }
    [data-testid="collapsedControl"] svg {
        color: white !important;
        fill: white !important;
    }

    /* 4. INDESTRUCTIBLE CONFIGURATION BUTTON TARGETING */
    [data-testid="stMain"] [data-testid="stButton"] {
        position: fixed !important;
        bottom: 40px !important;
        right: 40px !important;
        z-index: 9999999 !important;
        width: auto !important;
        pointer-events: auto !important;
    }
    
    [data-testid="stMain"] [data-testid="stButton"] button[kind="secondary"] {
        background-color: #4CAF50 !important;
        color: white !important;
        border: none !important;
        border-radius: 50px !important; 
        padding: 15px 30px !important;
        font-size: 16px !important;
        font-weight: bold !important;
        box-shadow: 0px 8px 20px rgba(0,0,0,0.4) !important;
        cursor: pointer !important;
        height: auto !important;
        transition: all 0.2s ease !important;
    }
    
    [data-testid="stMain"] [data-testid="stButton"] button[kind="secondary"] * {
        pointer-events: none !important; 
        color: white !important;
    }
    
    [data-testid="stMain"] [data-testid="stButton"] button[kind="secondary"]:hover {
        background-color: #45a049 !important;
        transform: scale(1.05) !important;
    }

    /* 5. FULL SCREEN MAP SETTINGS */
    iframe[title="streamlit_components.v1.components.html"] {
        position: fixed !important;
        top: 65px !important; 
        left: 0 !important;
        width: 100vw !important;
        height: calc(100vh - 65px) !important; 
        z-index: 1 !important;
        border: none !important;
    }

    /* 6. Ensure Sidebar behaves natively */
    section[data-testid="stSidebar"][aria-expanded="true"] {
        min-width: 450px !important;
        width: 450px !important;
        z-index: 9999999 !important;
    }

    /* 7. Spreadsheet Modal Styles */
    div[data-baseweb="popover"] > div {
        background-color: #2b303b !important;
        border: 2px solid #4CAF50 !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="popover"] li { color: #ffffff !important; font-weight: 600 !important; }
    div[data-baseweb="popover"] li:hover { background-color: #4CAF50 !important; }
</style>
""", unsafe_allow_html=True)

# INJECT THE TOP BAR BACKGROUND
st.markdown('<div class="top-bar-bg"></div>', unsafe_allow_html=True)

# ==========================================
# SIDEBAR SETUP
# ==========================================
with st.sidebar:
    st.title("⚙️ Parameters")
    st.header("📁 Load Data")
    with st.expander("Input Files", expanded=st.session_state.get("solver_run_count", 0) == 0):
        demand_file = st.text_input("Demand CSV", "5_city_Demand.csv")
        target_file = st.text_input("Target Time CSV", "5_city_Target_Time.csv")
        travel_file = st.text_input("Travel Time CSV", "5_city_Travel_Time.csv")
        coords_file = st.text_input("Coordinates CSV", "5_city_Coordinates.csv")
        max_k = st.number_input("Max Nodes per Cycle (k)", min_value=2, max_value=8, value=2)

    run_button = st.button("🚀 Run GLOP Optimizer", type="primary", use_container_width=True)

if "solver_run_count" not in st.session_state:
    st.session_state.solver_run_count = 0

if run_button:
    st.session_state.solver_run_count += 1
    st.session_state.active_k = max_k
    st.session_state.active_demand = demand_file
    st.session_state.active_target = target_file
    st.session_state.active_travel = travel_file
    st.session_state.active_coords = coords_file
    st.session_state.pop("data_loaded", None) 

# ==========================================
# 2. CACHED PHYSICS & BASELINE SOLVER
# ==========================================
def get_absolute_path(filename):
    if os.path.isabs(filename):
        return filename
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)

@st.cache_data 
def load_coordinates(filepath):
    try:
        abs_path = get_absolute_path(filepath)
        df = pd.read_csv(abs_path, index_col=0)
        return {str(idx): (float(row.iloc[0]), float(row.iloc[1])) for idx, row in df.iterrows()}, "Success"
    except FileNotFoundError:
        return None, f"File Not Found at {abs_path}"
    except Exception as e:
        return None, f"Error: {str(e)}"

@st.cache_data 
def generate_baseline(demand_path, target_path, travel_path, k):
    try:
        df_demand = pd.read_csv(get_absolute_path(demand_path), index_col=0)
        df_target = pd.read_csv(get_absolute_path(target_path), index_col=0)
        df_travel = pd.read_csv(get_absolute_path(travel_path), index_col=0)
    except FileNotFoundError:
        return None, "File Not Found"

    cities = df_demand.columns.tolist()
    demand_data, target_data, travel_data = {}, {}, {}
    for o in cities:
        for d in cities:
            if o != d and df_demand.loc[o,d] > 0:
                demand_data[(f"{o} ➔ {d}")] = float(df_demand.loc[o,d])
                target_data[(o,d)] = df_target.loc[o,d]
                travel_data[(o,d)] = df_travel.loc[o,d]

    unique_routes = set()
    for current_k in range(2, k + 1):
        for subset in itertools.combinations(cities, current_k):
            start_node = min(subset)
            stack = [([start_node], {node: 0 for node in subset})]
            stack[0][1][start_node] = 1
            while stack:
                path, counts = stack.pop()
                curr = path[-1]
                if curr == start_node and len(path) > 1:
                    if all(counts[n] >= 1 for n in subset):
                        cycle = path[:-1]
                        min_node = min(cycle)
                        min_indices = [i for i, x in enumerate(cycle) if x == min_node]
                        best_rot = min(cycle[idx:] + cycle[:idx] for idx in min_indices)
                        unique_routes.add(tuple(best_rot + [best_rot[0]]))
                        continue
                if len(path) >= 2 * current_k - 1: continue
                for neighbor in subset:
                    if neighbor != curr and counts[neighbor] + 1 <= (3 if neighbor == start_node else 2):
                        new_counts = counts.copy()
                        new_counts[neighbor] += 1
                        stack.append((path + [neighbor], new_counts))
                        
    routes = sorted(list(unique_routes), key=lambda x: (len(set(x)), len(x), x))
    route_strings = [" ➔ ".join(r) for r in routes]

    p_cost, valid_routes_for_od, flows_on_route_leg = {}, {k: [] for k in demand_data.keys()}, {}
    for r_idx, path in enumerate(routes):
        r_str = route_strings[r_idx]
        route_legs, total_time = [], 0
        for i in range(len(path) - 1):
            route_legs.append((path[i], path[i+1]))
            total_time += travel_data.get((path[i], path[i+1]), 1000)
        p_cost[r_str] = total_time

        for od_str in demand_data.keys():
            org, dst = od_str.split(" ➔ ")
            valid_path_found, legs_used = False, []
            for io in [i for i, x in enumerate(path[:-1]) if x == org]:
                for id_ in [i for i, x in enumerate(path[:-1]) if x == dst]:
                    segment_time, temp_legs, curr_idx, steps = 0, [], io, 0
                    while steps < len(route_legs):
                        leg = route_legs[curr_idx]
                        temp_legs.append(leg)
                        segment_time += travel_data.get(leg, 1000)
                        curr_idx = curr_idx + 1 if curr_idx + 1 < len(route_legs) else 0
                        steps += 1
                        if curr_idx == id_:
                            if segment_time <= target_data.get((org, dst), 0):
                                valid_path_found, legs_used = True, temp_legs
                            break
                if valid_path_found: break
            if valid_path_found:
                valid_routes_for_od[od_str].append(r_str)
                for (u, v) in legs_used:
                    if (r_str, u, v) not in flows_on_route_leg: flows_on_route_leg[(r_str, u, v)] = []
                    flows_on_route_leg[(r_str, u, v)].append(od_str)

    solver = pywraplp.Solver.CreateSolver('GLOP')
    y = {r: solver.NumVar(0.0, solver.infinity(), "") for r in route_strings}
    valid_f_indices = [(od, r) for od in demand_data.keys() for r in valid_routes_for_od[od]]
    f = {(od, r): solver.NumVar(0.0, solver.infinity(), "") for (od, r) in valid_f_indices}

    obj = solver.Objective()
    for r in route_strings: obj.SetCoefficient(y[r], p_cost[r])
    obj.SetMinimization()

    for od, dem in demand_data.items():
        c = solver.Constraint(dem, dem, "")
        for r in valid_routes_for_od[od]: c.SetCoefficient(f[(od, r)], 1.0)

    for r in route_strings:
        path = r.split(" ➔ ")
        for (u, v) in list(dict.fromkeys([(path[i], path[i+1]) for i in range(len(path)-1)])):
            valid_ks = flows_on_route_leg.get((r, u, v), [])
            if valid_ks:
                c = solver.Constraint(-solver.infinity(), 0.0, "")
                c.SetCoefficient(y[r], -1.0)
                for od in valid_ks: c.SetCoefficient(f[(od, r)], 1.0)

    solver.Solve()
    
    opt_y = {r: y[r].solution_value() for r in route_strings if y[r].solution_value() > 0.001}
    opt_f = {(od, r): f[(od, r)].solution_value() for (od, r) in valid_f_indices if f[(od, r)].solution_value() > 0.001}

    return demand_data, p_cost, flows_on_route_leg, valid_routes_for_od, opt_y, opt_f, "Success"

# ==========================================
# 3. POPUP WINDOW DEFINITION (The Dialog)
# ==========================================
@st.dialog("⚙️ Configure Fleet & Cargo", width="large")
def configuration_modal(route_options, demand_options):
    st.write("Edit your configuration below. Select the checkbox on the left of any row to access the delete toolbar.")
    
    st.subheader("🚚 Fleet Manager")
    edited_fleet = st.data_editor(
        st.session_state.df_fleet, 
        num_rows="dynamic", 
        use_container_width=True,
        column_config={
            "Route": st.column_config.SelectboxColumn("Route", options=route_options, required=True),
            "Assigned Trucks": st.column_config.NumberColumn("Trucks", min_value=0.0, step=0.25, default=0.0)
        },
        key="fleet_editor_modal"
    )

    st.markdown("---")

    st.subheader("📦 Cargo Manifest")
    edited_cargo = st.data_editor(
        st.session_state.df_cargo,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Demand": st.column_config.SelectboxColumn("Demand", options=demand_options, required=True),
            "Assigned Route": st.column_config.SelectboxColumn("Route", options=route_options, required=True),
            "Loaded Volume": st.column_config.NumberColumn("Vol", min_value=0.0, step=0.25, default=0.0)
        },
        key="cargo_editor_modal"
    )

    if st.button("💾 Apply Configuration & Close", type="primary", use_container_width=True):
        valid_routes_formatted = edited_fleet[edited_fleet["Assigned Trucks"] > 0]["Route"].dropna().tolist()
        cargo_drops = []
        for idx in edited_cargo.index:
            route_assigned = edited_cargo.loc[idx, "Assigned Route"]
            if pd.notna(route_assigned) and route_assigned not in valid_routes_formatted:
                cargo_drops.append(idx)
        if cargo_drops:
            edited_cargo = edited_cargo.drop(index=cargo_drops).reset_index(drop=True)

        st.session_state.df_fleet = edited_fleet.reset_index(drop=True)
        st.session_state.df_cargo = edited_cargo.reset_index(drop=True)
        st.rerun()

# ==========================================
# 4. APPLICATION LOGIC
# ==========================================
if st.session_state.solver_run_count == 0:
    st.markdown("<div style='position:absolute; top:40%; left:50%; transform:translate(-50%, -50%); z-index:999999; font-family:sans-serif; font-size:20px; font-weight:bold; color:#333; background:rgba(255,255,255,0.95); padding:20px 40px; border-radius:10px; border:2px solid #4CAF50; box-shadow:0 4px 20px rgba(0,0,0,0.3);'>👈 Open the sidebar to load your data and run the optimizer.</div>", unsafe_allow_html=True)
    m = folium.Map(location=[21.0, 78.0], zoom_start=5.5, tiles="CartoDB positron")
    
    scroll_kill = "<style>html, body {height: 100vh !important; width: 100vw !important; overflow: hidden !important; position: fixed !important; top: 0 !important; left: 0 !important;} .folium-map {height: 100vh !important; width: 100vw !important; position: absolute !important; top: 0; left: 0;}</style>"
    final_html = m.get_root().render().replace("</body>", f"{scroll_kill}</body>")
    components.html(final_html, height=1000) 
else:
    data_payload = generate_baseline(
        st.session_state.active_demand, 
        st.session_state.active_target, 
        st.session_state.active_travel, 
        st.session_state.active_k
    )
    
    city_coords, coord_status = load_coordinates(st.session_state.active_coords)

    if data_payload and data_payload[1] == "File Not Found":
        st.markdown("<div style='position:absolute; top:40%; left:50%; transform:translate(-50%, -50%); z-index:999999; font-family:sans-serif; font-size:20px; font-weight:bold; color:white; background:rgba(220,53,69,0.95); padding:20px 40px; border-radius:10px; box-shadow:0 4px 20px rgba(0,0,0,0.3);'>❌ Problem CSV Files Not Found. Check directory.</div>", unsafe_allow_html=True)
        m = folium.Map(location=[21.0, 78.0], zoom_start=5.5, tiles="CartoDB positron")
        scroll_kill = "<style>html, body {height: 100vh !important; width: 100vw !important; overflow: hidden !important; position: fixed !important; top: 0 !important; left: 0 !important;} .folium-map {height: 100vh !important; width: 100vw !important; position: absolute !important; top: 0; left: 0;}</style>"
        final_html = m.get_root().render().replace("</body>", f"{scroll_kill}</body>")
        components.html(final_html, height=1000)
    elif coord_status != "Success":
        st.markdown(f"<div style='position:absolute; top:40%; left:50%; transform:translate(-50%, -50%); z-index:999999; font-family:sans-serif; font-size:16px; font-weight:bold; color:white; background:rgba(220,53,69,0.95); padding:20px 40px; border-radius:10px; box-shadow:0 4px 20px rgba(0,0,0,0.3);'>❌ Coordinates Error: {coord_status}</div>", unsafe_allow_html=True)
        m = folium.Map(location=[21.0, 78.0], zoom_start=5.5, tiles="CartoDB positron")
        scroll_kill = "<style>html, body {height: 100vh !important; width: 100vw !important; overflow: hidden !important; position: fixed !important; top: 0 !important; left: 0 !important;} .folium-map {height: 100vh !important; width: 100vw !important; position: absolute !important; top: 0; left: 0;}</style>"
        final_html = m.get_root().render().replace("</body>", f"{scroll_kill}</body>")
        components.html(final_html, height=1000)
    else:
        demand_data, p_cost, flows_on_route_leg, valid_routes_for_od, opt_y, opt_f, _ = data_payload

        route_options = [f"{r} 🔹 Cost: {p_cost[r]:.2f}" for r in p_cost.keys()]
        demand_options = [f"{od} 🔸 Req: {req:.2f}" for od, req in demand_data.items()]

        if "data_loaded" not in st.session_state or st.session_state.get("app_version") != "v57_rounding_tolerance":
            st.session_state.baseline_cost = sum(opt_y[r] * p_cost[r] for r in opt_y)
            st.session_state.opt_y = opt_y 
            
            fleet_rows = [{"Route": f"{r} 🔹 Cost: {p_cost[r]:.2f}", "Assigned Trucks": round(trucks, 2)} for r, trucks in opt_y.items()]
            st.session_state.df_fleet = pd.DataFrame(fleet_rows)
            
            cargo_rows = [{"Demand": f"{od} 🔸 Req: {demand_data[od]:.2f}", "Assigned Route": f"{r} 🔹 Cost: {p_cost[r]:.2f}", "Loaded Volume": round(vol, 2)} for (od, r), vol in opt_f.items()]
            st.session_state.df_cargo = pd.DataFrame(cargo_rows)
            
            st.session_state.data_loaded = True
            st.session_state.app_version = "v57_rounding_tolerance" 

        # The Bulletproof Configuration Button 
        if st.button("⚙️ Configuration Panel"):
            configuration_modal(route_options, demand_options)

        # ==========================================
        # 5. THE ARITHMETIC REFEREE (With Tolerance)
        # ==========================================
        TOLERANCE = 0.05 # Allows up to 0.05 deviation to absorb UI rounding artifacts
        
        manual_y = {}
        for _, row in st.session_state.df_fleet.iterrows():
            if pd.notna(row["Route"]):
                r_raw = row["Route"].split(" 🔹 Cost:")[0]
                manual_y[r_raw] = manual_y.get(r_raw, 0) + row["Assigned Trucks"]

        manual_f = {}
        for _, row in st.session_state.df_cargo.iterrows():
            if pd.notna(row["Demand"]) and pd.notna(row["Assigned Route"]):
                od_raw = row["Demand"].split(" 🔸 Req:")[0]
                r_raw = row["Assigned Route"].split(" 🔹 Cost:")[0]
                manual_f[(od_raw, r_raw)] = manual_f.get((od_raw, r_raw), 0) + row["Loaded Volume"]

        total_cost = sum(trucks * p_cost[r] for r, trucks in manual_y.items() if trucks > 0 and r in p_cost)
        errors = []

        demand_totals = {od: 0.0 for od in demand_data.keys()}
        for (od, r), vol in manual_f.items():
            if od in demand_totals: demand_totals[od] += vol

        for od, req in demand_data.items():
            loaded = demand_totals[od]
            if loaded < req - TOLERANCE:
                errors.append(f"<b>Shortfall:</b> <span style='color:#b3d4ff; font-weight:bold;'>{od}</span> requires {req:.2f} trucks, but only {loaded:.2f} loaded.")
            elif loaded > req + TOLERANCE:
                errors.append(f"<b>Over-serviced:</b> <span style='color:#b3d4ff; font-weight:bold;'>{od}</span> requires {req:.2f} trucks, but {loaded:.2f} loaded.")

        leg_loads = {}
        for (od, r), vol in manual_f.items():
            if vol <= 0: continue
            if r not in valid_routes_for_od.get(od, []):
                errors.append(f"<b>Physics Error:</b> Cargo <span style='color:#b3d4ff;'>{od}</span> cannot arrive using route <span style='color:#ffc107;'>{r}</span>.")
                continue
            
            path = r.split(" ➔ ")
            org, dst = od.split(" ➔ ")
            cycle_len = len(path) - 1
            best_legs, min_len = [], 999
            for idx_o in [i for i, x in enumerate(path[:-1]) if x == org]:
                for idx_d in [i for i, x in enumerate(path[:-1]) if x == dst]:
                    curr, steps, legs = idx_o, 0, []
                    while curr != idx_d and steps < cycle_len:
                        nxt = curr + 1
                        legs.append((path[curr], path[nxt]))
                        curr = nxt if nxt < cycle_len else 0
                        steps += 1
                    if steps < min_len: min_len, best_legs = steps, legs
            
            for (u, v) in best_legs:
                leg_key = (r, u, v)
                leg_loads[leg_key] = leg_loads.get(leg_key, 0.0) + vol

        for (r, u, v), cargo_vol in leg_loads.items():
            assigned_trucks = manual_y.get(r, 0.0)
            if cargo_vol > assigned_trucks + TOLERANCE:
                errors.append(f"<b>Overloaded Leg:</b> Route <span style='color:#ffc107;'>{r}</span> leg <span style='color:#b3d4ff;'>{u} ➔ {v}</span> has {cargo_vol:.2f} cargo but only {assigned_trucks:.2f} trucks.")

        is_baseline_config = True
        for r, tr in st.session_state.opt_y.items():
            if abs(tr - manual_y.get(r, 0.0)) > TOLERANCE: is_baseline_config = False
        for r, tr in manual_y.items():
            if tr > 0 and abs(tr - st.session_state.opt_y.get(r, 0.0)) > TOLERANCE: is_baseline_config = False

        # ==========================================
        # 6. RENDER FULL SCREEN MAP & FIXED HTML ALERTS
        # ==========================================
        if len(errors) == 0:
            if is_baseline_config:
                alert_html = f'''<div style="position: fixed; top: 20px; right: 20px; z-index: 9999; background: rgba(40,167,69,0.95); color: white; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-family: sans-serif; box-shadow: 0 4px 15px rgba(0,0,0,0.4); backdrop-filter: blur(5px);">✅ Feasible | Cost: {total_cost:.2f} <span style="font-size:12px; font-weight:normal; margin-left: 10px;">(Optimal Baseline)</span></div>'''
            elif abs(total_cost - st.session_state.baseline_cost) < TOLERANCE:
                alert_html = f'''<div style="position: fixed; top: 20px; right: 20px; z-index: 9999; background: rgba(23,162,184,0.95); color: white; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-family: sans-serif; box-shadow: 0 4px 15px rgba(0,0,0,0.4); backdrop-filter: blur(5px);">🌟 Alternate Optimal! | Cost: {total_cost:.2f}</div>'''
            else:
                alert_html = f'''<div style="position: fixed; top: 20px; right: 20px; z-index: 9999; background: rgba(40,167,69,0.95); color: white; padding: 12px 20px; border-radius: 8px; font-weight: bold; font-family: sans-serif; box-shadow: 0 4px 15px rgba(0,0,0,0.4); backdrop-filter: blur(5px);">✅ Feasible | Cost: {total_cost:.2f}</div>'''
        else:
            err_lis = "".join([f"<li style='margin-bottom: 6px;'>{err}</li>" for err in errors])
            alert_html = f'''<div style="position: fixed; top: 20px; right: 20px; z-index: 9999; background: rgba(220,53,69,0.95); color: white; padding: 15px 20px; border-radius: 8px; font-family: sans-serif; box-shadow: 0 4px 20px rgba(0,0,0,0.5); max-width: 400px; max-height: 80vh; overflow-y: auto; backdrop-filter: blur(5px);">
                <div style="font-weight: bold; font-size: 16px; border-bottom: 1px solid rgba(255,255,255,0.3); padding-bottom: 8px; margin-bottom: 10px;">❌ Infeasible | Cost: {total_cost:.2f}</div>
                <ul style="margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.4;">{err_lis}</ul>
            </div>'''

        def generate_bold_colors(num):
            return ['#{:02x}{:02x}{:02x}'.format(*(int(c*255) for c in colorsys.hls_to_rgb((i * 0.618034)%1.0, 0.40, 0.85))) for i in range(num)]
        
        active_routes_map = {}
        palette = generate_bold_colors(len([r for r, t in manual_y.items() if t > 0]))
        color_idx = 0
        for r_raw, trucks in manual_y.items():
            if trucks > 0:
                active_routes_map[r_raw] = {'seq': r_raw.split(" ➔ "), 'trucks': trucks, 'color': palette[color_idx]}
                color_idx += 1

        active_flows_map = {}
        for (od_raw, r_raw), flow_val in manual_f.items():
            if flow_val <= 0 or r_raw not in active_routes_map: continue
            if od_raw not in active_flows_map: active_flows_map[od_raw] = {'total': 0, 'routes': [], 'legs_used': {}, 'volumes': {}}
            active_flows_map[od_raw]['total'] += flow_val
            active_flows_map[od_raw]['routes'].append(r_raw)
            active_flows_map[od_raw]['volumes'][r_raw] = flow_val
            
            path = r_raw.split(" ➔ ")
            org, dst = od_raw.split(" ➔ ")
            best_legs, min_len = [], 999
            for idx_o in [i for i, x in enumerate(path[:-1]) if x == org]:
                for idx_d in [i for i, x in enumerate(path[:-1]) if x == dst]:
                    curr, steps, legs = idx_o, 0, []
                    while curr != idx_d and steps < len(path)-1:
                        nxt = curr + 1
                        legs.append((path[curr], path[nxt]))
                        curr = nxt if nxt < len(path)-1 else 0
                        steps += 1
                    if steps < min_len: min_len, best_legs = steps, legs
            active_flows_map[od_raw]['legs_used'][r_raw] = [f"{u}-{v}" for (u, v) in best_legs]

        def get_bezier_curve(p1, p2, base_offset=0.15, max_bulge=1.0):
            d_lat, d_lon = p2[0]-p1[0], p2[1]-p1[1]
            length = math.sqrt(d_lat**2 + d_lon**2)
            if length == 0: return [p1] * 50
            eff = min(base_offset * length, max_bulge) / length
            c_lat, c_lon = (p1[0]+p2[0])/2 + d_lon*eff, (p1[1]+p2[1])/2 + -d_lat*eff
            return [(((1-t/49)**2)*p1[0] + 2*(1-t/49)*(t/49)*c_lat + ((t/49)**2)*p2[0], ((1-t/49)**2)*p1[1] + 2*(1-t/49)*(t/49)*c_lon + ((t/49)**2)*p2[1]) for t in range(50)]

        def get_arrowhead(p_prev, p_mid, length=0.45, angle=30, indent=0.55):
            d_lon, d_lat, avg_lat = (p_mid[1]-p_prev[1])*math.cos(math.radians((p_prev[0]+p_mid[0])/2)), p_mid[0]-p_prev[0], math.radians((p_prev[0]+p_mid[0])/2)
            h = math.atan2(d_lat, d_lon)
            return [p_mid, (p_mid[0]+length*math.sin(h+math.pi+math.radians(angle)), p_mid[1]+(length*math.cos(h+math.pi+math.radians(angle)))/math.cos(avg_lat)), (p_mid[0]+(length*indent)*math.sin(h+math.pi), p_mid[1]+((length*indent)*math.cos(h+math.pi))/math.cos(avg_lat)), (p_mid[0]+length*math.sin(h+math.pi-math.radians(angle)), p_mid[1]+(length*math.cos(h+math.pi-math.radians(angle)))/math.cos(avg_lat))]

        if city_coords:
            avg_lat = sum(c[0] for c in city_coords.values()) / len(city_coords)
            avg_lon = sum(c[1] for c in city_coords.values()) / len(city_coords)
        else:
            avg_lat, avg_lon = 21.0, 78.0

        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=5.5, tiles="CartoDB positron")
        
        for city, coord in city_coords.items():
            folium.CircleMarker(location=coord, radius=8, color="black", fill=True, fill_color="white", fill_opacity=1, weight=3, z_index_offset=1000).add_to(m)
            folium.Marker(location=coord, icon=folium.DivIcon(html=f'<div style="font-size: 14pt; font-family: sans-serif; font-weight: bold; color: #333; transform: translate(15px, -15px); text-shadow: 2px 2px 4px white;">{city}</div>')).add_to(m)

        leg_tracker = {}
        for r_raw, data in active_routes_map.items():
            for i in range(len(data['seq']) - 1):
                city_A, city_B = data['seq'][i], data['seq'][i+1]
                
                if city_A not in city_coords or city_B not in city_coords:
                    continue
                
                leg = (city_A, city_B)
                leg_tracker[leg] = leg_tracker.get(leg, 0) + 1
                curve = get_bezier_curve(city_coords[city_A], city_coords[city_B], 0.15 + ((leg_tracker[leg] - 1) * 0.1), 1.0 + ((leg_tracker[leg] - 1) * 0.8))
                safe_id = r_raw.replace(" ➔ ", "") 
                folium.PolyLine(curve, color=data['color'], weight=max(2.5, data['trucks'] * 2), opacity=0.8, className=f"route-path r-{safe_id} leg-{city_A}-{city_B}").add_to(m)
                folium.Polygon(get_arrowhead(curve[24], curve[25]), color=data['color'], weight=1, fill=True, fill_color=data['color'], fill_opacity=1.0, className=f"route-arrow r-{safe_id} leg-{city_A}-{city_B}", line_join='miter').add_to(m)

        js_flow = json.dumps({k: {'total': v['total'], 'routes': [r.replace(" ➔ ", "") for r in v['routes']], 'legs_used': {r.replace(" ➔ ", ""): v['legs_used'][r] for r in v['legs_used']}, 'volumes': {r.replace(" ➔ ", ""): v['volumes'][r] for r in v['volumes']}} for k, v in active_flows_map.items()})
        js_route = json.dumps({r_raw.replace(" ➔ ", ""): {'seq': r_raw, 'trucks': d['trucks'], 'color': d['color']} for r_raw, d in active_routes_map.items()})
        
        ui_html = f'''
        <style id="dynamic-highlight">
            path.leaflet-interactive {{ stroke-linejoin: miter !important; stroke-linecap: butt !important; transition: opacity 0.2s, stroke-width 0.2s, stroke-dasharray 0.2s; }}
        </style>
        
        <style>
            html, body {{
                height: 100vh !important;
                width: 100vw !important;
                overflow: hidden !important;
                margin: 0 !important;
                padding: 0 !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
            }}
            .folium-map {{
                height: 100vh !important;
                width: 100vw !important;
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
            }}
            .leaflet-top.leaflet-left {{ top: auto !important; bottom: 30px !important; }}
        </style>

        <div style="position: fixed; top: 15px; left: 80px; z-index: 9999; background: rgba(255,255,255,0.95); padding: 6px; border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); font-family: sans-serif; display: flex; gap: 8px;">
            <button id="btn-routes" onclick="switchMode('routes')" style="padding: 8px 15px; border: none; background: #333; color: white; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px;">Fleet Routes</button>
            <button id="btn-flows" onclick="switchMode('flows')" style="padding: 8px 15px; border: none; background: #ddd; color: #333; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px;">Commodity Flows</button>
        </div>
        
        <div id="floating-info-panel" style="position: fixed; top: 90px; right: 20px; width: auto; min-width: 300px; max-width: 450px; border: 1px solid rgba(0,0,0,0.2); border-radius: 6px; z-index: 9999; background-color: rgba(255, 255, 255, 0.95); padding: 12px; box-shadow: 2px 4px 15px rgba(0,0,0,0.2); font-family: sans-serif; display: none;"></div>
        
        <div id="panel-routes" style="position: fixed; top: 70px; left: 80px; width: auto; min-width: 300px; max-width: 450px; max-height: calc(100vh - 150px); border: 1px solid rgba(0,0,0,0.2); border-radius: 8px; z-index: 9999; background-color: rgba(255, 255, 255, 0.95); overflow-y: auto; padding: 15px; box-shadow: 2px 4px 15px rgba(0,0,0,0.2); font-family: sans-serif; box-sizing: border-box;">
            <h5 style="margin-top: 0; margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; font-size: 14px;">Active Fleet Options</h5>
            <ul style="list-style-type: none; padding-left: 0; margin: 0; font-size: 12px;">
        '''
        for r_raw, data in active_routes_map.items():
            safe_id = r_raw.replace(" ➔ ", "")
            ui_html += f'<li style="margin-bottom: 6px; display: flex; align-items: flex-start; cursor: pointer; padding: 4px 6px; border-radius: 4px; transition: background 0.2s;" onmouseenter="hoverRoute(\'{safe_id}\', \'{data["color"]}\'); this.style.background=\'#e9ecef\';" onmouseleave="resetMap(); this.style.background=\'transparent\';"><span style="background-color: {data["color"]}; min-width: 12px; height: 12px; display: inline-block; border-radius: 50%; margin-right: 8px; margin-top: 2px; border: 1px solid #777; flex-shrink: 0;"></span><span style="word-break: break-word; line-height: 1.4;"><b>{data["trucks"]:.2f}</b> | {r_raw}</span></li>'
        
        ui_html += '''</ul></div>
        <div id="panel-flows" style="position: fixed; top: 70px; left: 80px; width: auto; min-width: 300px; max-width: 450px; max-height: calc(100vh - 150px); border: 1px solid rgba(0,0,0,0.2); border-radius: 8px; z-index: 9999; background-color: rgba(255, 255, 255, 0.95); overflow-y: auto; padding: 15px; box-shadow: 2px 4px 15px rgba(0,0,0,0.2); font-family: sans-serif; box-sizing: border-box; display: none;">
            <h5 style="margin-top: 0; margin-bottom: 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; font-size: 14px;">Commodity Demands</h5>
            <ul style="list-style-type: none; padding-left: 0; margin: 0; font-size: 12px;">
        '''
        for od_raw, data in sorted(active_flows_map.items(), key=lambda item: item[1]['total'], reverse=True):
            ui_html += f'<li style="margin-bottom: 6px; display: flex; align-items: flex-start; cursor: pointer; padding: 4px 6px; border-radius: 4px; transition: background 0.2s;" onmouseenter="hoverFlow(\'{od_raw}\'); this.style.background=\'#d1ecf1\';" onmouseleave="resetMap(); this.style.background=\'transparent\';"><span style="word-break: break-word; line-height: 1.4;">📦 <b>{data["total"]:.2f} T</b> | {od_raw}</span></li>'
        
        ui_html += f'''</ul></div>
        <script>
            const flowData = {js_flow}; const routeData = {js_route};
            function switchMode(mode) {{
                document.getElementById('btn-routes').style.background = mode==='routes'?'#333':'#ddd'; document.getElementById('btn-routes').style.color = mode==='routes'?'white':'#333';
                document.getElementById('btn-flows').style.background = mode==='flows'?'#333':'#ddd'; document.getElementById('btn-flows').style.color = mode==='flows'?'white':'#333';
                document.getElementById('panel-routes').style.display = mode==='routes'?'block':'none'; document.getElementById('panel-flows').style.display = mode==='flows'?'block':'none';
                resetMap();
            }}
            function hoverRoute(r, c) {{
                document.body.classList.add('route-hover-active');
                document.getElementById('floating-info-panel').style.display = 'block';
                document.getElementById('floating-info-panel').innerHTML = `<h5 style="margin-top:0; margin-bottom:8px; border-bottom:2px solid ${{c}}; padding-bottom:4px;">Route Focus</h5><div style="font-size:13px; line-height:1.5;"><b>Path:</b> <span style="word-break: break-word;">${{routeData[r].seq}}</span><br><b>Fleet:</b> <span style="color:${{c}}; font-weight:bold;">${{routeData[r].trucks.toFixed(2)}} Trucks</span></div>`;
                document.getElementById('dynamic-highlight').innerHTML = `path.leaflet-interactive {{ stroke-linejoin: miter !important; stroke-linecap: butt !important; }} body.route-hover-active path.leaflet-interactive:not([stroke="black"]) {{ opacity: 0.1 !important; }} body.route-hover-active path.r-${{r}}.route-path {{ opacity: 1 !important; stroke-width: 8px !important; z-index: 9999; }} body.route-hover-active path.r-${{r}}.route-arrow {{ opacity: 1 !important; stroke-width: 2px !important; z-index: 9999; }}`;
                document.querySelectorAll(`.r-${{r}}`).forEach(p => p.parentNode.appendChild(p));
            }}
            function hoverFlow(k) {{
                document.body.classList.add('flow-hover-active');
                let bHtml = `<ul style="margin-top:4px; padding-left:15px; margin-bottom: 0;">`;
                flowData[k].routes.forEach(r => {{ if(routeData[r].trucks > 0) {{ bHtml += `<li style="margin-bottom: 4px;"><span style="color:${{routeData[r].color}}; font-weight:bold; word-break: break-word;">${{routeData[r].seq}}</span><br>➔ <b>${{flowData[k].volumes[r].toFixed(2)}} T</b></li>`; }} }});
                bHtml += `</ul>`;
                document.getElementById('floating-info-panel').style.display = 'block';
                document.getElementById('floating-info-panel').innerHTML = `<h5 style="margin-top:0; margin-bottom:8px; border-bottom:2px solid #333; padding-bottom:4px;">Flow Focus</h5><div style="font-size:13px; line-height:1.5;"><b>Demand:</b> <span style="word-break: break-word;">${{k}}</span><br><b>Volume:</b> <span style="font-weight:bold;">${{flowData[k].total.toFixed(2)}} Trucks</span><br><b>Routes:</b> ${{bHtml}}</div>`;
                let css = `path.leaflet-interactive {{ stroke-linejoin: miter !important; stroke-linecap: butt !important; }} body.flow-hover-active path.leaflet-interactive:not([stroke="black"]) {{ opacity: 0.05 !important; }}`;
                flowData[k].routes.forEach(r => {{
                    css += `body.flow-hover-active path.r-${{r}}.route-path {{ opacity: 0.4 !important; stroke-width: 4px !important; stroke-dasharray: 8 8 !important; }} body.flow-hover-active path.r-${{r}}.route-arrow {{ opacity: 0 !important; }}`;
                    flowData[k].legs_used[r].forEach(leg => {{
                        css += `body.flow-hover-active path.r-${{r}}.leg-${{leg}}.route-path {{ opacity: 1 !important; stroke-width: 8px !important; stroke-dasharray: none !important; }} body.flow-hover-active path.r-${{r}}.leg-${{leg}}.route-arrow {{ opacity: 1 !important; stroke-width: 2px !important; }}`;
                        document.querySelectorAll(`.r-${{r}}.leg-${{leg}}`).forEach(p => p.parentNode.appendChild(p));
                    }});
                }});
                document.getElementById('dynamic-highlight').innerHTML = css;
            }}
            function resetMap() {{ document.body.classList.remove('route-hover-active', 'flow-hover-active'); document.getElementById('dynamic-highlight').innerHTML = `path.leaflet-interactive {{ stroke-linejoin: miter !important; stroke-linecap: butt !important; transition: opacity 0.2s, stroke-width 0.2s, stroke-dasharray 0.2s; }}`; document.getElementById('floating-info-panel').style.display = 'none'; }}
        </script>
        '''
        
        map_html = m.get_root().render()
        final_html = map_html.replace("</body>", f"{ui_html}{alert_html}</body>")
        components.html(final_html, height=1000)
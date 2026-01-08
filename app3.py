import streamlit as st
import numpy as np
from scipy.interpolate import PchipInterpolator

st.set_page_config(page_title="Drone Endurance Calculator", layout="centered")
st.title("🚁 Agriculture Drone Endurance Calculator")

# =========================================================
# Motor Thrust vs Current Table Input
# =========================================================
st.header("Motor Thrust vs Current Data (Per Motor)")

default_motor_data = {
    "Thrust (g)": [
        1499, 2001, 2498, 2997, 3500, 4001, 4998, 5500, 6003, 6500,
        7005, 7504, 7999, 8999, 9505, 10000, 10503, 10994, 11494, 11852
    ],
    "Current (A)": [
        2.4, 3.6, 4.9, 6.3, 8.0, 9.7, 13.5, 15.6, 17.6, 19.9,
        22.1, 24.9, 27.4, 32.9, 36.1, 38.6, 42.6, 45.5, 48.8, 51.8
    ]
}

motor_df = st.data_editor(
    default_motor_data,
    num_rows="dynamic",
    use_container_width=True
)

thrust_g = np.array(motor_df["Thrust (g)"], dtype=float)
current_A = np.array(motor_df["Current (A)"], dtype=float)

current_interp = PchipInterpolator(thrust_g, current_A, extrapolate=True)

# =========================================================
# Drone Configuration
# =========================================================
st.header("Drone Configuration")

col1, col2 = st.columns(2)

with col1:
    motors = st.number_input("Number of Motors", min_value=1, value=6)
    empty_weight = st.number_input("Empty Weight (kg)", value=13.15)
    battery_weight = st.number_input("Battery Weight (kg)", value=4.8)
    payload_weight = st.number_input("Variable Payload Weight (kg)", value=10.0)

with col2:
    max_battery_Ah = st.number_input("Max Battery Capacity (Ah)", value=30.0)
    battery_limit = st.number_input("Battery Consumption Limit (%)", value=80.0)
    electronics_consumption = st.number_input(
        "Electronics Consumption (A)",
        value=4.274
    )

battery_Ah = max_battery_Ah * (battery_limit / 100)

dry_kg = empty_weight + battery_weight
total_kg_start = dry_kg + payload_weight

# =========================================================
# Advanced Settings
# =========================================================
with st.expander("⚙️ Advanced Settings"):
    st.subheader("Mission Timings")
    takeoff_time_sec = st.number_input("Takeoff Time (sec)", value=15.0)
    landing_time_sec = st.number_input("Landing Time (sec)", value=15.0)

    st.subheader("Pump Settings")
    flow_rate = st.number_input("Pump Flow Rate (L/min)", value=3.333)

    st.subheader("T/W Ratios")
    tw_ratio_takeoff = st.number_input("Takeoff T/W Ratio", value=1.10)
    tw_ratio_hover_dispense = st.number_input("Hover & Dispense T/W Ratio", value=1.05)
    tw_ratio_landing = st.number_input("Landing T/W Ratio", value=0.80)

# =========================================================
# Calculate Button
# =========================================================
if st.button("🧮 Calculate Endurance"):

    takeoff_time = takeoff_time_sec / 60
    landing_time = landing_time_sec / 60

    dispense_duration_min = payload_weight / flow_rate
    dispense_duration_sec = dispense_duration_min * 60

    # =====================
    # Takeoff
    # =====================
    thrust_takeoff = (total_kg_start * 1000 * tw_ratio_takeoff) / motors
    I_takeoff = current_interp(thrust_takeoff)
    I_total_takeoff = (I_takeoff * motors) + electronics_consumption
    Ah_takeoff = I_total_takeoff * takeoff_time / 60

    # =====================
    # Dispense (time-marching)
    # =====================
    dt = 0.1
    Ah_dispense = 0.0

    for t in np.arange(0, dispense_duration_sec, dt):
        water_left = max(payload_weight - (flow_rate / 60) * t, 0)
        total_weight = dry_kg + water_left
        thrust = (total_weight * 1000 * tw_ratio_hover_dispense) / motors
        I_motor = current_interp(thrust)
        I_total = (I_motor * motors) + electronics_consumption
        Ah_dispense += (I_total * dt) / 3600

    # =====================
    # Landing (empty payload)
    # =====================
    thrust_landing = (dry_kg * 1000 * tw_ratio_landing) / motors
    I_landing = current_interp(thrust_landing)
    I_total_landing = (I_landing * motors) + electronics_consumption
    Ah_landing = I_total_landing * landing_time / 60

    # =====================
    # Hover Current (empty payload)
    # =====================
    thrust_hover = (dry_kg * 1000 * tw_ratio_hover_dispense) / motors
    I_hover = current_interp(thrust_hover)
    hover_current_total = (I_hover * motors) + electronics_consumption

    # =====================
    # Original Outputs (unchanged physics)
    # =====================
    Ah_hover = battery_Ah - Ah_takeoff - Ah_dispense - Ah_landing
    hovering_time = Ah_hover * 60 / hover_current_total

    MTOW_HOVER_UNTIL_RTL = takeoff_time + landing_time + hovering_time
    MTOW_DISPENSE_HOVER_UNTIL_RTL = (
        takeoff_time + dispense_duration_min + landing_time + hovering_time
    )

    # =====================
    # Corrected Refill Cycle Logic
    # =====================
    remaining_Ah = battery_Ah
    cycles = 0.0
    total_time_min = 0.0

    while remaining_Ah >= (Ah_takeoff + Ah_landing):
        remaining_Ah -= Ah_takeoff
        total_time_min += takeoff_time

        if remaining_Ah >= (Ah_dispense + Ah_landing):
            remaining_Ah -= Ah_dispense
            total_time_min += dispense_duration_min
            cycles += 1.0
        else:
            usable_Ah = remaining_Ah - Ah_landing
            fraction = usable_Ah / Ah_dispense
            fraction = max(0.0, min(fraction, 1.0))

            total_time_min += dispense_duration_min * fraction
            cycles += fraction
            remaining_Ah = Ah_landing

        remaining_Ah -= Ah_landing
        total_time_min += landing_time

    max_cycles = cycles
    MTOW_DISPENSE_REFILL_UNTIL_RTL = total_time_min

    # =====================
    # Display Results
    # =====================
    st.success("Calculation Complete")

    st.write(f"✅ **Estimated Number of Mission Cycles:** {max_cycles:.2f}")
    st.write(
        f"⏱️ **Takeoff – Hover until RTL – Land:** "
        f"{MTOW_HOVER_UNTIL_RTL:.2f} minutes"
    )
    st.write(
        f"⏱️ **Takeoff – Dispense once – Hover – Land:** "
        f"{MTOW_DISPENSE_HOVER_UNTIL_RTL:.2f} minutes"
    )
    st.write(
        f"⏱️ **Takeoff – Dispense – Land (Repeat until RTL):** "
        f"{MTOW_DISPENSE_REFILL_UNTIL_RTL:.2f} minutes"
    )

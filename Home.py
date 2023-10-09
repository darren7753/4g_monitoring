import streamlit as st
import os
import datetime

from multi_pages import Daily_Weekly_Monthly, Hourly
from firebase_admin import credentials, initialize_app, auth, _apps
from cryptography.fernet import Fernet
from streamlit_option_menu import option_menu

def main():
    st.set_page_config(
        page_title="4G Monitoring - TSEL EID",
        layout="wide"
    )

    reduce_header_height_style = """
        <style>
            div.block-container {
                padding-top: 1rem;
                padding-bottom: 1rem;
            }
        </style>
    """
    st.markdown(reduce_header_height_style, unsafe_allow_html=True)

    hide_decoration_bar_style = """
        <style>
            header {visibility: hidden;}
            footer {visibility: hidden;}
        </style>
    """
    st.markdown(hide_decoration_bar_style, unsafe_allow_html=True)

    def load_credentials():
        with open("encryption_key_firebase.key", "rb") as key_file:
            key = key_file.read()
        # key = os.environ.get("FIREBASE_KEY")
        cipher = Fernet(key)

        with open("encrypted_credentials_firebase.enc", "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()
        decrypted_data = cipher.decrypt(encrypted_data)

        return credentials.Certificate(eval(decrypted_data.decode()))
    
    def generate_title(period, site_id):
        return f"{period} Site {site_id.upper()}"

    def render_dwm_inputs():
        title_slot_dwm = st.empty()
        st.markdown(f"<h3>🔍 Filters</h3>", unsafe_allow_html=True)

        col1, col2, col3, col4, col5 = st.columns([0.5, 1, 0.5, 0.5, 0.5])

        current_site_id_dwm = col1.text_input(label="Site ID", value="saa108")
        current_period_dwm = col3.selectbox(
            label="Period",
            options=["Daily", "Weekly", "Monthly"]
        )
        band_dwm = col2.multiselect(
            label="Band",
            options=["L1800", "L2100", "L2300", "L900"],
            default=["L1800", "L2100", "L2300", "L900"]
        )
        start_date_dwm = col4.date_input(label="Start Date", value=datetime.date(2023, 7, 1))
        today_dwm = datetime.datetime.now().date()
        end_date_dwm = col5.date_input(label="End Date", value=today_dwm + datetime.timedelta(hours=7))

        title_dwm = generate_title(current_period_dwm, current_site_id_dwm)
        title_slot_dwm.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{title_dwm}</h1>", unsafe_allow_html=True)

        st.session_state.site_id_dwm = current_site_id_dwm
        st.session_state.period_dwm = current_period_dwm
        st.session_state.band_dwm = band_dwm
        st.session_state.start_date_dwm = start_date_dwm
        st.session_state.end_date_dwm = end_date_dwm

        title_dwm = generate_title(current_period_dwm, current_site_id_dwm)
        title_slot_dwm.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{title_dwm}</h1>", unsafe_allow_html=True)

    def render_hourly_inputs():
        title_slot = st.empty()
        st.markdown(f"<h3>🔍 Filters</h3>", unsafe_allow_html=True)
        
        col1, col2, col3, col4, col5 = st.columns([0.5, 1, 0.5, 0.5, 0.5])

        current_site_id_hourly = col1.text_input(label="Site ID", value="saa108")
        current_period_hourly = col3.selectbox(
            label="Period",
            options=["Hourly"]
        )
        band_hourly = col2.multiselect(
            label="Band",
            options=["L1800", "L2100", "L2300", "L900"],
            default=["L1800", "L2100", "L2300", "L900"]
        )
        start_date = col4.date_input(label="Start Date", value=datetime.date(2023, 9, 28))
        today = datetime.datetime.now().date()
        end_date = col5.date_input(label="End Date", value=today + datetime.timedelta(hours=7))

        title = generate_title(current_period_hourly, current_site_id_hourly)
        title_slot.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{title}</h1>", unsafe_allow_html=True)

        st.session_state.site_id_hourly = current_site_id_hourly
        st.session_state.period_hourly = current_period_hourly
        st.session_state.band_hourly = band_hourly
        st.session_state.start_date_hourly = start_date
        st.session_state.end_date_hourly = end_date

        title = generate_title(current_period_hourly, current_site_id_hourly)
        title_slot.markdown(f"<h1 style='text-align: center; margin-bottom: 20px;'>{title}</h1>", unsafe_allow_html=True)

    def main_page():
        with st.container():
            page_option = option_menu(
                menu_title=None,
                options=["Home", "Daily", "Hourly"],
                icons=["house-fill", "1-square-fill", "2-square-fill"],
                orientation="horizontal"
            )

            if page_option == "Home":
                st.write(f"Hello {st.session_state['user_email']}, you're logged in!")
                if st.button("Sign Out"):
                    st.session_state["logged_in"] = False
                    st.session_state["user_email"] = ""
                    st.rerun()
                
            elif page_option == "Daily":
                render_dwm_inputs()
                with st.spinner("Loading..."):
                    Daily_Weekly_Monthly.app()

            elif page_option == "Hourly":
                render_hourly_inputs()
                with st.spinner("Loading..."):
                    Hourly.app()

    def login_signup_page():
        st.markdown(f"""
            <div style='display: flex; justify-content: center; align-items: center; margin-bottom: 20px;'>
                <h1 style='margin-right: -40px;'>Welcome</h1>
                <img src="https://media.giphy.com/media/hvRJCLFzcasrR4ia7z/giphy.gif" style='vertical-align: middle;' width="45">
            </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col2:
            email = st.text_input("Email", placeholder="Enter your email")
            password = st.text_input("Password", placeholder="Enter your password", type="password")
            
            if st.button("Log In"):
                if email == "" or password == "":
                    st.warning("Please fill in the blanks.")
                else:
                    check_account(email, password)

    def check_account(email, password):
        try:
            user_by_email = auth.get_user_by_email(email)
        except auth.UserNotFoundError:
            st.error("User not found. Please sign up first.")
            return

        try:
            user_by_uid = auth.get_user(password)
            if user_by_email.uid == user_by_uid.uid:
                st.session_state["logged_in"] = True
                st.session_state["user_email"] = email
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
        except auth.UserNotFoundError:
            st.error("Incorrect password. Please try again.")

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if "user_email" not in st.session_state:
        st.session_state["user_email"] = ""

    creds = load_credentials()
    if not _apps:
        initialize_app(creds)

    if st.session_state["logged_in"]:
        main_page()
    else:
        login_signup_page()

if __name__ == "__main__":
    main()
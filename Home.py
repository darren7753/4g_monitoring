import streamlit as st
import os

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
            footer {visibility: hidden;}
        </style>
    """
    st.markdown(hide_decoration_bar_style, unsafe_allow_html=True)

    def load_credentials_firebase():
        try:
            with open("encryption_key_firebase.key", "rb") as key_file:
                key = key_file.read()
        except FileNotFoundError:
            key = os.environ.get("FIREBASE_KEY")

        cipher = Fernet(key)

        with open("encrypted_credentials_firebase.enc", "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()
        decrypted_data = cipher.decrypt(encrypted_data)

        return credentials.Certificate(eval(decrypted_data.decode()))

    def main_page():
        with st.container():
            page_option = option_menu(
                menu_title=None,
                options=["Home", "Daily", "Hourly"],
                icons=["house-fill", "1-square-fill", "2-square-fill"],
                orientation="horizontal"
            )

            if page_option == "Home":
                st.markdown(f"<h3>Hello <a href='mailto:{st.session_state['user_email']}'>{st.session_state['user_email']}</a>, you're logged in!</h3>", unsafe_allow_html=True)
                if st.button("Sign Out"):
                    st.session_state["logged_in"] = False
                    st.session_state["user_email"] = ""
                    st.rerun()
                
            elif page_option == "Daily":
                left_right_padding_style = """
                    <style>
                        div.block-container {
                            padding-left: 1rem;
                            padding-right: 1rem;
                        }
                    </style>
                """
                st.markdown(left_right_padding_style, unsafe_allow_html=True)

                with st.spinner("Loading..."):
                    Daily_Weekly_Monthly.app()

            elif page_option == "Hourly":
                left_right_padding_style = """
                    <style>
                        div.block-container {
                            padding-left: 1rem;
                            padding-right: 1rem;
                        }
                    </style>
                """
                st.markdown(left_right_padding_style, unsafe_allow_html=True)

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

    creds = load_credentials_firebase()
    if not _apps:
        initialize_app(creds)

    if st.session_state["logged_in"]:
        main_page()
    else:
        login_signup_page()

if __name__ == "__main__":
    main()
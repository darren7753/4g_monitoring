import streamlit as st
import os

from multi_pages import Daily_Weekly_Monthly, Hourly
from firebase_admin import credentials, initialize_app, auth, _apps
from cryptography.fernet import Fernet

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
        # with open("encryption_key_firebase.key", "rb") as key_file:
        #     key = key_file.read()
        key = os.environ.get("FIREBASE_KEY")
        cipher = Fernet(key)

        with open("encrypted_credentials_firebase.enc", "rb") as encrypted_file:
            encrypted_data = encrypted_file.read()
        decrypted_data = cipher.decrypt(encrypted_data)

        return credentials.Certificate(eval(decrypted_data.decode()))

    def main_page():
        with st.container():
            page_option = st.sidebar.radio("Choose your page:", ["Home", "Daily-Weekly-Monthly", "Hourly"])

            if 'last_page' not in st.session_state:
                st.session_state.last_page = None

            if st.session_state.last_page == "Daily-Weekly-Monthly" and page_option == "Hourly":
                if 'end_date_dwm' in st.session_state:
                    del st.session_state['end_date_dwm']

            st.session_state.last_page = page_option

            if page_option == "Home":
                st.write(f"Hello {st.session_state['user_email']}, you're logged in!")
                if st.button("Sign Out"):
                    st.session_state["logged_in"] = False
                    st.session_state["user_email"] = ""
                    st.rerun()
                st.write("You're on the home page!")
            elif page_option == "Daily-Weekly-Monthly":
                Daily_Weekly_Monthly.app()
            elif page_option == "Hourly":
                Hourly.app()

    def login_signup_page():
        st.markdown(f"""
            <div style='display: flex; justify-content: center; align-items: center;'>
                <h1 style='margin-right: -40px;'>Welcome</h1>
                <img src="https://media.giphy.com/media/hvRJCLFzcasrR4ia7z/giphy.gif" width="45">
            </div>
        """, unsafe_allow_html=True)
        
        choice = st.selectbox("", ["Log In", "Sign Up"], label_visibility="collapsed")
        
        email = st.text_input("Email", placeholder="Enter your email")
        password = st.text_input("Password", placeholder="Enter your password", type="password")
        
        if choice == "Log In":
            if st.button("Log In"):
                if email == "" or password == "":
                    st.warning("Please fill in the blanks.")
                else:
                    check_account(email, password)

        else:
            if st.button("Sign Up"):
                if email == "" or password == "":
                    st.warning("Please fill in the blanks.")
                else:
                    try:
                        user = auth.create_user(email=email, uid=password)
                        st.success("Your account has been created successfully!")
                    except Exception as e:
                        st.error(f"Error: {e}")

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

import streamlit as st

import os
from main import csi

def main():


    # Add pages to the app
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox("What you wanna do today?", ["Upload Audio", "Chat"])
    st.write("Team Quixotic Sapiens")
    st.title("Speech Data Analysis")

    if page == "Upload Audio":

        uploaded_file = st.file_uploader("Upload your audio file here:", type=["wav", "mp3"])

        if uploaded_file is not None:
            st.write("File uploaded successfully!..Wait for the report..")
            content = uploaded_file.getvalue()
                
                # You can save the content to a temporary file if necessary
            with open("temp.wav", "wb") as f:
                f.write(content)
            # Initialize the csi object with the API key
            app = csi('Intel/neural-chat-7b-v3-3')
            # Process the audio file
            result = app.process("temp.wav")
            
            # Display the processed result
            st.write("Processed Result:")
            st.write(result)
    if page == "Chat":
        st.write("Chat with the AI")
        user_input = st.text_input("You: ")
        if st.button("Send"):
            dotenv_path = "C:/Users/jayan/Music/INTEL-AI-HACKATHON/.env"
            obj = LLM(api_base="https://openai-demetrius.openai.azure.com/", api_version="2023-07-01-preview", api_key=os.getenv('OPENAI_API_KEY'))

            res = obj.generate(user_input)
            print(res)
            st.write(res)


if __name__ == "__main__":
    main()

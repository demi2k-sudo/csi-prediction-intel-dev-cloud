import os
import streamlit as st
from main import csi 
import dotenv

# Load environment variables from .env file
dotenv.load_dotenv()

# Access the API key from the environment variables
api_key = os.environ.get("OPENAI_API_KEY")


st.title("Audio Processing with CSI")

uploaded_file = st.file_uploader("Upload an audio file", type=["wav"])

if uploaded_file is not None:
    st.audio(uploaded_file, format='audio/wav')

    if st.button('Process'):
        with st.spinner('Processing...'):
            content = uploaded_file.getvalue()
                
                # You can save the content to a temporary file if necessary
            with open("temp.wav", "wb") as f:
                f.write(content)
            # Initialize the csi object with the API key
            app = csi(api_base="https://openai-demetrius.openai.azure.com/", 
                    api_version="2023-07-01-preview",
                    api_key=api_key)
            # Process the audio file
            result = app.process("temp.wav")
            
            # Display the processed result
            st.write("Processed Result:")
            st.write(result)

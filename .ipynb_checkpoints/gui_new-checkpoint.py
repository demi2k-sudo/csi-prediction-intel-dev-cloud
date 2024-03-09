
import streamlit as st

import os
from main import csi

from streamlit_chat import message
import transformers

if "tokeniser" not in st.session_state:
    st.session_state.tokeniser = transformers.AutoTokenizer.from_pretrained("Intel/neural-chat-7b-v3-3")
if "model" not in st.session_state:
    st.session_state.model = transformers.AutoModelForCausalLM.from_pretrained("Intel/neural-chat-7b-v3-3")
if "result" not in st.session_state:
    st.session_state.result = None
if "transcripts" not in st.session_state:
    st.session_state.transcripts = None

if "messages" not in st.session_state:
    st.session_state.messages = []
if "conmessages" not in st.session_state:
    st.session_state.conmessages = []


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
            app = csi('Intel/neural-chat-7b-v3-3',st.session_state.model,st.session_state.tokeniser)
            # Process the audio file
            st.session_state.result,st.session_state.transcripts = app.process_return_with_transcripts("temp.wav")
            
            # Display the processed result
            st.write("Processed Result:")
            st.write(st.session_state.result)

     
            

    if page == "Chat":
        
        
        
            
        
        st.session_state.messages = [f"### System:You are a customer service expert\n### User:{st.session_state.transcripts}\n### Assistant:{st.session_state.result}"]
        
        # with st.sidebar:
        user_input = st.text_input("Your message: ", key="user_input")

        if user_input:
            
            st.session_state.conmessages.append(user_input)
            
            prompt = st.session_state.messages.append(f"\n### User:\n{user_input}\n### Assistant:\n")
            prompt = " ".join(st.session_state.messages)
            print(prompt)
            inputs = st.session_state.tokeniser.encode(prompt, return_tensors="pt", add_special_tokens=False)
            outputs = st.session_state.model.generate(inputs, max_length=10000, num_return_sequences=1)
            response = st.session_state.tokeniser.decode(outputs[0], skip_special_tokens=True)
            print(response)
            test = response.split("### Assistant:\n")[-1]
            st.session_state.conmessages.append(test)

            
            messages_d = st.session_state.conmessages
            for i, msg in enumerate(messages_d):
                if i % 2 != 0:
                    message(msg, is_user=True, key=str(i) + '_user')
                else:
                    message(msg, is_user=False, key=str(i) + '_ai')
        


if __name__ == "__main__":
    main()
    
    
    

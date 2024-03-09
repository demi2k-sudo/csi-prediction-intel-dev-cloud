# CSI Prediction on Intel Dev Cloud (Team Quixotic Sapiens - Intel AI Hackathon)

<a href="https://drive.google.com/file/d/1enbwoTAkZygtp7K2Xytqkyr-eKwokHDx/view?usp=sharing">Check out demo here!<a>
## What is our project about? ##
We have developed an AI-powered customer satisfaction analysis application for businesses leveraging call recordings as input data. This project revolutionises the way businesses understand and improve customer satisfaction by harnessing the power of artificial intelligence to analyze call recordings. By extracting valuable insights from customer interactions, the application aims to provide businesses with a comprehensive understanding of customer sentiments, concerns, and satisfaction levels. 

This analysis will enable businesses to identify patterns, trends, and areas for improvement in their customer service processes and interactions. By leveraging AI-driven sentiment analysis and other advanced techniques, the application seeks to streamline the process of CSI measurement, enabling businesses to proactively address customer needs, enhance customer experiences, and ultimately drive higher levels of satisfaction and loyalty.

## What is CSI? ##
Let's say you're a bank manager, and you want to know how satisfied your customers are with the services you provide. So, you might send out surveys asking questions like, "Were you satisfied with the speed of service?" or "Did our staff assist you well?"

Customers respond, giving their feedback. The bank then compiles this information to create a Customer Satisfaction Index (CSI). If the CSI is high, it means most customers are happy with the bank's services. But if it's low, it indicates there might be issues that need to be addressed, like long wait times or unfriendly staff.

So, just like you'd want to make sure your friends had a great time at a party you hosted, the bank wants to ensure their customers are happy with the banking experience. The CSI helps them gauge satisfaction levels
and make improvements where needed to keep customers coming back.

## Modules Used ##
We've made use of a variety of modules such as:
- **Intel® Neural Chat**
- **OpenAI Whisper**
- **SpeechBrain**
- **Streamlit**
- **Transformers (HuggingFace)**
- **Azure Communication Services (azure.communication.mail)**

## How do we implement it? ##

<p align="center">
  <img width="auto" height="auto" src="https://github.com/jayanzth/intel-ai-hackathon/assets/93752903/7cdc1d07-83c6-4895-ba60-6e0d0af7e9f7">
</p>


1. **Call Audio**: The process begins with collecting call audio recordings, which serve as the primary input for the customer satisfaction analysis.

2. **Whisper & Speechbrain**: The call audio undergoes processing using tools like Whisper and Speechbrain. These tools are used to perform tasks such as Speech Transription, and Emotion Detection, corresponding to each timestamp.

3. **Prompt Template and Instructions**: After transcription, the instructions along with the previously generated inferences are compiled into a prompt template for further processing.

4. **LLM (Neural Chat)**: The prompt template is sent to the LLM (**Intel® Neural Chat**), which processes the given template, making use of the instructions provided earlier.

   <blockquote>
      example = "Communication: 8.5/10 Resolution: 8/10 Emotion Handling: 7/10. So, the overall Customer Satisfaction Index can be calculated as the average of these three scores, which is approximately 7.8/10."
    </blockquote>
    
    And the user template would be:
    <br><br>

   <blockquote>
      user_input = f"I will provide you with the transcripts of a customer service call. I will also provide you the tone of the voices at each timestamp.('a': Anger 'h': Happy 'n': Neutral) You have to analyse          both and come up with a Customer Satisfaction Index<Transcripts of the talks>\n{transcripts}<Transcripts of the talks\>\n<Tone and emotion of the voice>\n{emotions}<\Tone and emotion of the        voice>\n<Example>\n{example}<Example\>"
      </blockquote>

6. **Detailed Report**: The output from the LLM is further processed to generate a detailed report summarizing the analysis results. This report includes insights, trends, and recommendations derived from the conversation data, providing businesses with actionable information to improve customer satisfaction.

7. **Prompt (with inputs as Conversation Buffer and User Queries)**: Following the report generation, a new prompt is created based on the conversation buffer and any user queries. This prompt serves as input for the next stage of the flow, enabling continuous interaction and refinement of analysis outcomes.

8. **Chatbot**: The prompt is then fed into a chatbot, which interacts with users to address queries, provide additional information, or gather feedback.

9. **Answer**: Finally, the chatbot generates responses based on the input prompt, user queries, and conversation buffer, delivering answers or engaging in conversation to support ongoing analysis and decision-making. The user queries and inferences are sent back to the Conversation Buffer to maintain a feedback loop.

10. **Email**: Before the LLM analyses the emotions and transcripts as mentioned in (4), it checks if there's an issue with the attitude of the official and sends an email to the management using Azure communication service highlighting the issues.
  

## Cloud Architecture ##

We have our complete project running on Intel Dev Cloud Instance with the following specifications,
<p align="center">
  <img width="auto" height="auto" src="https://github.com/jayanzth/intel-ai-hackathon/assets/85375873/7d2e858e-8e60-41ad-869c-6ed7358b70ad">
</p>

Also we use Secure shell to forward the necessary ports from our VM to local machine.
<p align="center">
  <img width="auto" height="auto" src="https://github.com/jayanzth/intel-ai-hackathon/assets/93752903/cea74522-bab3-4d2b-a5db-75d35718acb9">
</p>

We forward port:8888 to access Jupyter notebooks for development and port:8501 for accessing streamlit UI.

## Overview ##

**gui_new.py**
This script serves as the main entry point for the Streamlit application. It provides a user interface for uploading audio files of customer service calls and interacting with the system. The significance of this file lies in its ability to seamlessly integrate various functionalities and provide a user-friendly interface for users to analyze customer service calls.

**main.py**
This file contains the csi class, which encapsulates the core functionality of the application. It coordinates the processing of audio files, transcription of speech, and generation of responses. Additionally, it utilizes other modules such as gpt, speech_brain_app, transcription, and mail to achieve these tasks. The significance of this file lies in its role as the orchestrator of the entire analysis pipeline.

**gpt.py**
The HF_LLM class defined in this file is responsible for initializing a transformer-based language model for generating responses based on given inputs. This file plays a crucial role in natural language processing within the application, as it enables the system to understand and generate human-like responses based on customer service transcripts and emotions extracted from audio.

**speech_brain_app.py**
This file contains functionality to extract emotions from audio files using SpeechBrain's diarization model. Emotion detection is an essential aspect of customer service analysis, as it provides insights into the emotional state of both customers and service representatives during calls. This file enhances the application's ability to provide comprehensive feedback on customer interactions.

**transcription.py**
Utilizing Hugging Face's pipeline for automatic speech recognition, this file transcribes audio files into text. Transcription forms the foundation of the application's analysis process by converting spoken words into a format that can be processed and analyzed further. The significance of this file lies in its role in converting audio data into a readable format for analysis.

**mail.py**
This file handles the sending of emails using the Azure Communication Service. It contains functionality to assess customer service calls and send emails based on the analysis conducted by the application. Email communication is crucial for providing feedback and taking necessary actions based on the analysis results, making this file an essential component of the application's workflow.

## Quickstart ##

Install all the necessary libraries needed using pip/pip3

<blockquote>
  pip install -r requirements.txt
</blockquote>

Start the streamlit server>>>>>>

<blockquote>
  streamlit run gui_new.py
</blockquote>

**Screenshots**
<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/3a8f5c96-57af-4dad-8793-7e3539790a7d">
</p>

<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/844a27fb-8723-4121-aa23-489197c37638">
</p>

<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/e0dd3662-f0d5-4e32-97a3-7246adea7c60">
</p>

<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/e0dd3662-f0d5-4e32-97a3-7246adea7c60">
</p>

<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/cda67b97-6aee-4fe4-8964-1a55e441c6ef">
</p>

<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/d1172d88-e096-4965-b682-f5b76c60bf23">
</p>

<p align="center">
  <img width="auto" height="auto" src="https://github.com/demi2k-sudo/csi-prediction-intel-dev-cloud/assets/85375873/d75555d7-4fb9-4fcb-ab07-03c5da058ba9">
</p>









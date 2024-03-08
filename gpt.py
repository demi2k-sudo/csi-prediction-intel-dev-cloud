import transformers


class HF_LLM:
    
    def __init__(self, model_name):
        self.model = transformers.AutoModelForCausalLM.from_pretrained(model_name)
        self.tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)
        self.model_name = model_name

# model_name = 'Intel/neural-chat-7b-v3-3'
# model = transformers.AutoModelForCausalLM.from_pretrained(model_name)
# tokenizer = transformers.AutoTokenizer.from_pretrained(model_name)

    def generate_response(self, transcripts, emotions, system_input="You are a Customer Service expert!" ):

        example = "Communication: 8.5/10 Resolution: 8/10 Emotion Handling: 7/10. So, the overall Customer Satisfaction Index can be calculated as the average of these three scores, which is approximately 7.8/10."
        user_input = f"I will provide you with the transcripts of a customer service call. I will also provide you the tone of the voices at each timestamp.('a': Anger 'h': Happy 'n': Neutral) You have to analyse both and come up with a Customer Satisfaction Index<Transcripts of the talks>\n{transcripts}<Transcripts of the talks\>\n<Tone and emotion of the voice>\n{emotions}<\Tone and emotion of the voice>\n<Example>\n{example}<Example\>"

        # Format the input using the provided template
        prompt = f"### System:\n{system_input}\n### User:\n{user_input}\n### Assistant:\n"

        # Tokenize and encode the prompt
        inputs = self.tokenizer.encode(prompt, return_tensors="pt", add_special_tokens=False)

        # Generate a response
        outputs = self.model.generate(inputs, max_length=10000, num_return_sequences=1)
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Extract only the assistant's response
        return response.split("### Assistant:\n")[-1]














# import openai
# from dotenv import load_dotenv
# load_dotenv()

# class LLM:
    
#     def __init__(self, api_base, api_version, api_key):
#         self.api_base = api_base
#         self.api_version = api_version
#         self.api_key = api_key
        
    
#     def get_csi(self, transcripts, emotions):
#         openai.api_type = "azure"
#         openai.api_base = self.api_base#"https://openai-demetrius.openai.azure.com/"
#         openai.api_version = self.api_version#"2023-07-01-preview"
#         openai.api_key = self.api_key#dotenv.get_key(key_to_get="OPENAI_API_KEY", dotenv_path = "F:\Software-Project\Sport-Highlights\LLM\.env")      
#         example = "Communication: 8.5/10 Resolution: 8/10 Emotion Handling: 7/10. So, the overall Customer Satisfaction Index can be calculated as the average of these three scores, which is approximately 7.8/10."
#         message_text = [{"role":"system","content":f"I will provide you with the transcripts of a customer service call. I will also provide you the tone of the voices at each timestamp.('a': Anger 'h': Happy 'n': Neutral) You have to analyse both and come up with a Customer Satisfaction Index<Transcripts of the talks>\n{transcripts}<Transcripts of the talks\>\n<Tone and emotion of the voice>\n{emotions}<\Tone and emotion of the voice>\n<Example>\n{example}<Example\>"}]
#         self.completion = openai.ChatCompletion.create(
#         engine="gpt4-demetrius",
#         messages = message_text,
#         temperature=0.9,
#         max_tokens=5000,
#         top_p=0.95,
#         frequency_penalty=0,
#         presence_penalty=0,
#         stop=None
#         )
    
    
#         return self.completion
        




from main import csi 
import dotenv
#app = csi(api_base="https://openai-demetrius.openai.azure.com/",api_version="2023-07-01-preview",api_key=dotenv.get_key(key_to_get="OPENAI_API_KEY", dotenv_path = ".env"))
app = csi("Intel/neural-chat-7b-v3-3")
print(app.process(path='new.wav'))

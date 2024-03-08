from gpt import HF_LLM
from speech_brain_app import get_emotion
from transcription import Transcriptor


class csi:

    def __init__(self,model_name):
        self.gpt = HF_LLM(model_name)
        self.transcriptor = Transcriptor()

    def process(self, audio):
        emotions = get_emotion(audio)
        transcripts = self.transcriptor.transcribe(audio)
        result = self.gpt.generate_response(transcripts, emotions)
        return result

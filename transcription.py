import torch
from transformers import pipeline


class Transcriptor:
  def __init__(self):
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    self.pipe = pipeline(
      "automatic-speech-recognition",
      model="openai/whisper-large-v3",
      chunk_length_s=30,
      device=device,
      )
  
  def transcribe(self,audio): 
    prediction = self.pipe(audio, batch_size=8, return_timestamps=True)["chunks"]
    print(prediction)

    return prediction
    
    





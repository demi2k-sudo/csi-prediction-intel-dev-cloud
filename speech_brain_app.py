from speechbrain.inference.diarization import Speech_Emotion_Diarization

def get_emotion(audio):
    classifier = Speech_Emotion_Diarization.from_hparams(source="speechbrain/emotion-diarization-wavlm-large")
    diary = classifier.diarize_file(audio)
    return diary

#path = r"new.wav"
#print(get_emotion(path))

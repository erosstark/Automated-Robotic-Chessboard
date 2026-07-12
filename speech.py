import io
import re
import wave
import numpy as np
import speech_recognition as sr
from faster_whisper import WhisperModel

class VoiceController:
    """
    Gerencia o reconhecimento de voz usando o modelo Whisper local.
    Implementado como Gerenciador de Contexto para manter o microfone aberto.
    """
    TRADUCAO_PECAS = {
        "rei": "K", "rainha": "Q", "dama": "Q", "torre": "R",
        "bispo": "B", "cavalo": "N", "peão": "", "peao": "",
    }

    def __init__(self, model_size="small", device="cpu", compute_type="int8"):
        print(f"Carregando modelo Whisper ({model_size})...")
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone(sample_rate=16000)
        self.source = None
        self.prompt_xadrez = "O jogo de xadrez começou. Tabuleiro A1 A2. Tabuleiro Peão E4. Cavalo F3. Bispo C4."

    def __enter__(self):
        """Abre o microfone e calibra o ruído ambiente ao entrar no contexto."""
        print("\n[ Configurando Microfone... ]")
        self.source = self.microphone.__enter__()
        print("Calibrando ruído ambiente (aguarde 1.5s)...")
        self.recognizer.adjust_for_ambient_noise(self.source, duration=1.5)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Fecha o microfone ao sair do contexto."""
        if self.source:
            self.microphone.__exit__(exc_type, exc_val, exc_tb)

    def converter_audio_para_numpy(self, audio_data):
        """Converte áudio do SpeechRecognition para formato compatível com Whisper."""
        wav_dados = audio_data.get_wav_data()
        with wave.open(io.BytesIO(wav_dados), "rb") as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        return audio_np

    def extrair_comando(self, texto):
        """Analisa o texto em busca da wake word 'tabuleiro' e identifica a ação."""
        texto_limpo = texto.lower().strip()
        WAKE_WORD = "tabuleiro"

        if WAKE_WORD not in texto_limpo:
            return None

        # Comandos de Sistema
        if "encerrar o jogo" in texto_limpo:
            return ("system", "quit")
        if "ativar modo verboso" in texto_limpo:
            return ("system", "verbose_on")
        if "desativar modo verboso" in texto_limpo:
            return ("system", "verbose_off")

        # Extração de Jogada
        texto_comando = texto_limpo.replace(WAKE_WORD, "").strip()
        matches = re.findall(r'([a-h])\s*([1-8])', texto_comando)
        
        if not matches:
            return None
        
        if len(matches) == 2:
            uci = f"{matches[0][0]}{matches[0][1]}{matches[1][0]}{matches[1][1]}"
            return ("move_uci", uci)
            
        casa_destino = f"{matches[0][0]}{matches[0][1]}"
        letra_san = ""
        for peca_pt, letra_en in self.TRADUCAO_PECAS.items():
            if peca_pt in texto_comando:
                letra_san = letra_en
                break
        
        return ("move_san", f"{letra_san}{casa_destino}")

    def ouvir(self):
        """Escuta o microfone (que já deve estar aberto) e retorna o comando."""
        if not self.source:
            raise RuntimeError("O VoiceController deve ser usado dentro de um bloco 'with'.")

        try:
            # Escuta uma frase
            audio = self.recognizer.listen(self.source, timeout=None, phrase_time_limit=5)
            audio_np = self.converter_audio_para_numpy(audio)

            segmentos, _ = self.model.transcribe(
                audio_np, language="pt", initial_prompt=self.prompt_xadrez,
                beam_size=5, vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            textos_validos = [seg.text for seg in segmentos if seg.no_speech_prob < 0.4]
            texto_final = " ".join(textos_validos).strip()

            if texto_final:
                print(f"Ouvido: '{texto_final}'")
                return self.extrair_comando(texto_final)
            
        except Exception as e:
            print(f"Erro na captura de voz: {e}")
        return None

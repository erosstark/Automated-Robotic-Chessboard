import pandas as pd
import asyncio
import chess
import chess.engine
import time

# Tenta importar serial, se falhar o modo simulação será usado automaticamente
try:
    import serial
except ImportError:
    serial = None

from tabuleiro import BoardManager
from path import PathPlanner
from speech import VoiceController


class ChessApp:
    """
    Classe principal que integra o reconhecimento de voz, lógica de xadrez,
    planejamento de rotas e interface com o hardware (Arduino).
    """

    def __init__(self, engine_path, serial_port=None, verbose=True):
        self.verbose = verbose
        self.board = chess.Board()
        self.board_manager = BoardManager()
        self.path_planner = PathPlanner()
        self.voice_controller = VoiceController()
        self.engine_path = engine_path
        self.engine = None
        self.modo_jogo = "PvB"  # Default: Player vs Bot

        # Comunicação Serial
        self.serial_port = serial_port
        self.serial = None
        self.baudrate = 115200

        # Configurações do Pandas para visualização
        pd.set_option("display.max_rows", None)
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", None)

    async def initialize_engine(self):
        """Inicializa o motor Stockfish."""
        try:
            _, self.engine = await chess.engine.popen_uci(self.engine_path)
            self.log("Stockfish inicializado com sucesso.")
        except Exception as e:
            print(f"Erro ao inicializar Stockfish: {e}")
            print("O jogo continuará sem o Bot.")
            self.modo_jogo = "PvP"

    async def initialize_hardware(self):
        """Inicializa a conexão serial com o Arduino."""
        if not self.serial_port or not serial:
            print(
                "[AVISO] Hardware não configurado ou pyserial ausente. Modo SIMULAÇÃO ativo."
            )
            return

        try:
            self.serial = serial.Serial(self.serial_port, self.baudrate, timeout=2)
            # Espera o Arduino dar o reset e enviar "SISTEMA PRONTO"
            self.log(f"Conectando ao Arduino em {self.serial_port}...")

            # Aguarda a mensagem de pronto do Arduino
            start_time = time.time()
            while time.time() - start_time < 5:
                linha = self.serial.readline().decode().strip()
                if "SISTEMA PRONTO" in linha:
                    self.log("Arduino conectado e pronto!")
                    break

            # Garante que o Arduino está no Modo Jogo
            await self.enviar_comando_arduino("P")

        except Exception as e:
            print(f"Erro ao conectar ao Arduino em {self.serial_port}: {e}")
            self.serial = None

    def log(self, message):
        """Print de depuração se o modo verboso estiver ativo."""
        if self.verbose:
            print(f"[LOG] {message}")

    async def enviar_comando_arduino(self, tipo, payload=None):
        """
        Envia comandos para o Arduino seguindo o protocolo definido no Arduino.cpp.
        tipo: 'T' (trajetória), 'P' (modo jogo), 'C' (modo calibração), 'H' (home), 'D' (debug)
        payload: lista de coordenadas para o comando 'T'
        """
        if not self.serial:
            if payload:
                coords = [(node.x, node.y) for node in payload]
                print(f">>> SIMULAÇÃO HARDWARE: Enviando {tipo} com {coords}")
            else:
                print(f">>> SIMULAÇÃO HARDWARE: Enviando comando {tipo}")
            return

        def _read_line_with_check():
            linha = self.serial.readline().decode().strip()
            if not linha:  # Timeout (vazio)
                raise TimeoutError(
                    "Arduino não respondeu dentro do tempo limite (Timeout)."
                )
            return linha

        def _write_and_wait():
            try:
                if tipo == "T" and payload:
                    n = len(payload)
                    # Envia o comando inicial 'T{n}' para avisar a quantidade de pontos
                    init_msg = f"T{n}\n"
                    self.log(f"Enviando para Arduino: {init_msg.strip()}")
                    self.serial.write(init_msg.encode())

                    # Aguarda o Arduino responder READY_FOR_POINTS
                    while True:
                        linha = _read_line_with_check()
                        self.log(f"Arduino diz: {linha}")
                        if "READY_FOR_POINTS" in linha:
                            break

                    # Envia cada ponto individualmente e aguarda POINT_OK
                    for idx, node in enumerate(payload):
                        point_msg = f"{node.x} {node.y}\n"
                        self.log(f"Enviando ponto {idx+1}/{n}: {point_msg.strip()}")
                        self.serial.write(point_msg.encode())

                        while True:
                            linha = _read_line_with_check()
                            self.log(f"Arduino diz: {linha}")
                            if "POINT_OK" in linha:
                                break

                    # Aguarda a mensagem final de TRAJETORIA OK
                    while True:
                        linha = _read_line_with_check()
                        self.log(f"Arduino diz: {linha}")
                        if "TRAJETORIA OK" in linha:
                            break
                else:
                    msg = f"{tipo}\n"
                    self.log(f"Enviando para Arduino: {msg.strip()}")
                    self.serial.write(msg.encode())

                    esperar_ok = tipo in ["H", "K"]
                    if esperar_ok:
                        while True:
                            linha = _read_line_with_check()
                            self.log(f"Arduino diz: {linha}")
                            if "OK" in linha or "DEFINIDO" in linha:
                                break
                    else:
                        linha = _read_line_with_check()
                        self.log(f"Arduino diz: {linha}")
            except Exception as e:
                print(f"\n[ERRO DE HARDWARE] Falha na comunicação serial: {e}")
                print("[AVISO] Mudando automaticamente para modo SIMULAÇÃO.")
                if self.serial:
                    try:
                        self.serial.close()
                    except Exception:
                        pass
                self.serial = None

        await asyncio.to_thread(_write_and_wait)

    async def executar_movimento_fisico(self, move):
        """
        Coordena a movimentação no tabuleiro expandido, lidando com capturas,
        roque, en passant e promoção.
        """
        origem_uci = move.uci()[:2]
        destino_uci = move.uci()[2:4]
        is_capture = self.board.is_capture(move)
        is_castling = self.board.is_castling(move)
        is_en_passant = self.board.is_en_passant(move)
        promotion = move.promotion

        # 1. Lidar com Capturas (Normal ou En Passant)
        if is_capture:
            if is_en_passant:
                cap_uci = destino_uci[0] + origem_uci[1]
                self.log(f"Captura En Passant! Alvo em {cap_uci}")
            else:
                cap_uci = destino_uci

            peca_capturada = self.board_manager.grid.at[cap_uci[1], cap_uci[0]]
            if peca_capturada != "." and peca_capturada != "#":
                self.log(f"Captura detectada! Movendo {peca_capturada} para a lateral.")
                pos_lateral = self.board_manager.get_storage_position(peca_capturada)

                self.board_manager.erase_piece([cap_uci[0], cap_uci[1]])
                rota_cap = self.path_planner.calcular_rota(
                    self.board_manager.grid, [cap_uci[0], cap_uci[1]], pos_lateral
                )

                if self.verbose:
                    print("\n[LOG] Rota de Captura (Peça saindo do tabuleiro):")
                    print(
                        self.path_planner.visualizar_rota(
                            self.board_manager.grid, rota_cap
                        )
                    )

                rota_otim_cap = self.path_planner.otimizar_trajetoria(rota_cap)

                await self.enviar_comando_arduino("T", rota_otim_cap)
                self.board_manager.draw_piece(
                    pos_lateral, peca_capturada, with_markers=True
                )

        # 2. Lidar com Roque
        if is_castling:
            # Movimentação do Rei
            peca_rei = self.board_manager.grid.at[origem_uci[1], origem_uci[0]]
            self.board_manager.erase_piece([origem_uci[0], origem_uci[1]])
            rota_rei = self.path_planner.calcular_rota(
                self.board_manager.grid,
                [origem_uci[0], origem_uci[1]],
                [destino_uci[0], destino_uci[1]],
            )

            if self.verbose:
                print("\n[LOG] Rota do Rei no Roque:")
                print(
                    self.path_planner.visualizar_rota(self.board_manager.grid, rota_rei)
                )

            rota_otim_rei = self.path_planner.otimizar_trajetoria(rota_rei)
            await self.enviar_comando_arduino("T", rota_otim_rei)
            self.board_manager.draw_piece([destino_uci[0], destino_uci[1]], peca_rei)

            # Movimentação da Torre
            if destino_uci == "g1":
                torre_orig, torre_dest = "h1", "f1"
            elif destino_uci == "c1":
                torre_orig, torre_dest = "a1", "d1"
            elif destino_uci == "g8":
                torre_orig, torre_dest = "h8", "f8"
            elif destino_uci == "c8":
                torre_orig, torre_dest = "a8", "d8"

            peca_torre = self.board_manager.grid.at[torre_orig[1], torre_orig[0]]
            self.log(
                f"Roque: Movendo torre {peca_torre} de {torre_orig} para {torre_dest}"
            )
            self.board_manager.erase_piece([torre_orig[0], torre_orig[1]])
            rota_torre = self.path_planner.calcular_rota(
                self.board_manager.grid,
                [torre_orig[0], torre_orig[1]],
                [torre_dest[0], torre_dest[1]],
            )

            if self.verbose:
                print("\n[LOG] Rota da Torre no Roque:")
                print(
                    self.path_planner.visualizar_rota(
                        self.board_manager.grid, rota_torre
                    )
                )

            rota_otim_torre = self.path_planner.otimizar_trajetoria(rota_torre)
            await self.enviar_comando_arduino("T", rota_otim_torre)
            self.board_manager.draw_piece([torre_dest[0], torre_dest[1]], peca_torre)

        # 3. Movimentação Normal (inclui promoção)
        else:
            peca = self.board_manager.grid.at[origem_uci[1], origem_uci[0]]

            if promotion:
                cor = "W" if peca.isupper() else "B"
                promoted_char = chess.piece_symbol(promotion).upper()
                peca_final = promoted_char if cor == "W" else promoted_char.lower()
                self.log(f"PROMOÇÃO! {peca} promovido para {peca_final}")
            else:
                peca_final = peca

            self.board_manager.erase_piece([origem_uci[0], origem_uci[1]])
            rota = self.path_planner.calcular_rota(
                self.board_manager.grid,
                [origem_uci[0], origem_uci[1]],
                [destino_uci[0], destino_uci[1]],
            )

            if self.verbose:
                print(f"\n[LOG] Rota do Movimento ({origem_uci} -> {destino_uci}):")
                print(self.path_planner.visualizar_rota(self.board_manager.grid, rota))

            rota_otim = self.path_planner.otimizar_trajetoria(rota)
            await self.enviar_comando_arduino("T", rota_otim)
            self.board_manager.draw_piece([destino_uci[0], destino_uci[1]], peca_final)

        if self.verbose:
            print("\nTabuleiro físico atualizado:")
            print(self.board_manager)
        await self.enviar_comando_arduino("H")

    async def processar_comando(self, comando):
        """Processa o comando extraído da voz ou teclado."""
        if not comando:
            return

        tipo, valor = comando

        if tipo == "system":
            if valor == "quit":
                print("Encerrando jogo...")
                return "stop"
            elif valor == "verbose_on":
                self.verbose = True
                print("Modo verboso ativado.")
            elif valor == "verbose_off":
                self.verbose = False
                print("Modo verboso desativado.")
            elif valor == "home":
                print("Enviando motores para HOME...")
                await self.enviar_comando_arduino("H")
            elif valor == "debug":
                print("Togglado DEBUG no Arduino.")
                await self.enviar_comando_arduino("D")

        elif tipo in ["move_san", "move_uci"]:
            try:
                if tipo == "move_san":
                    move = self.board.parse_san(valor)
                else:
                    move = chess.Move.from_uci(valor)

                if move in self.board.legal_moves:
                    await self.executar_movimento_fisico(move)
                    self.board.push(move)
                    return "moved"
                else:
                    print(f"Jogada ilegal: {valor}")
            except Exception as e:
                print(f"Erro ao processar jogada: {e}")
        return None

    async def turno_bot(self):
        """Executa a jogada do motor Stockfish."""
        if not self.engine:
            return

        result = await self.engine.play(self.board, chess.engine.Limit(depth=10))
        move = result.move

        self.log(f"Bot joga: {move}")
        await self.executar_movimento_fisico(move)
        self.board.push(move)

    def escolher_modo(self):
        """Pergunta ao usuário qual o modo de jogo."""
        print("\n=== SELEÇÃO DE MODO ===")
        print("1. Jogador vs Bot (Stockfish)")
        print("2. Jogador vs Jogador (Local)")
        escolha = input("Escolha (1 ou 2): ").strip()
        self.modo_jogo = "PvP" if escolha == "2" else "PvB"
        print(f"Modo {self.modo_jogo} selecionado.")

    async def run(self):
        """Loop principal do jogo."""
        self.escolher_modo()

        # Inicializa subsistemas
        if self.modo_jogo == "PvB":
            await self.initialize_engine()

        await self.initialize_hardware()

        self.board_manager.preencher_por_fen(self.board.fen())

        print("\n=== XADREZ POR VOZ INICIADO ===")
        print("Comandos: 'Tabuleiro [Peça] [Casa]', 'Home', 'Debug' ou 'Sair'.")

        if self.verbose:
            print("\nTabuleiro Inicial:")
            print(self.board_manager)
            print(f"\nTabuleiro Lógico:\n{self.board}")

        try:
            with self.voice_controller:
                while not self.board.is_game_over():
                    jogador = "BRANCAS" if self.board.turn == chess.WHITE else "PRETAS"
                    print(f"\n[ Turno das {jogador} ]")

                    comando = await asyncio.to_thread(self.voice_controller.ouvir)
                    status = await self.processar_comando(comando)

                    if status == "stop":
                        break

                    if status == "moved":
                        if self.board.is_game_over():
                            break

                        if self.modo_jogo == "PvB":
                            print("\n[ Bot pensando... ]")
                            await self.turno_bot()

                    await asyncio.sleep(0.1)

            print(f"\nFIM DE JOGO! Resultado: {self.board.result()}")

        finally:
            if self.engine:
                await self.engine.quit()
            if self.serial:
                self.serial.close()


async def main():
    # Caminho do Stockfish
    engine_path =r"C:\Users\eross\OneDrive\Documents\Chess\stockfish-windows-x86-64-avx2\stockfish\stockfish-windows-x86-64-avx2.exe"

    # Se None, entra em modo simulação.
    serial_port = "COM14"

    app = ChessApp(engine_path, serial_port=serial_port)
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())

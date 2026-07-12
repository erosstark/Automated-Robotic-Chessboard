import pandas as pd
import numpy as np

class BoardManager:
    """
    Gerencia o tabuleiro expandido 37x37, permitindo desenhar e apagar peças,
    além de gerenciar as áreas de peças capturadas.
    """
    def __init__(self):
        self.grid = self._criar_grade_37x37()
        self.capturadas_brancas_pos = 0 # Contador para peças brancas capturadas
        self.capturadas_pretas_pos = 0  # Contador para peças pretas capturadas
        
        # Colunas de armazenamento das peças capturadas
        self.STORAGE_COL_E = 'E0'
        self.STORAGE_COL_D = 'D2'
        

    def _criar_grade_37x37(self):
        """Cria o DataFrame 37x37 com nomes de colunas e linhas específicos."""
        colunas = ['E0', 'E1', 'E2'] 
        letras = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
        p_count = 1
        
        for i in range(8):
            colunas.extend([f"{letras[i]}0", letras[i], f"{letras[i]}1"])
            if i < 7:
                colunas.extend([f"p{p_count}"])
                p_count += 1
        colunas.extend(['D0', 'D1', 'D2'])
        
        linhas = ['Top0', 'Top1', 'Top2']
        numeros = ['8', '7', '6', '5', '4', '3', '2', '1']
        l_count = 1
        
        for i in range(8):
            linhas.extend([f"{numeros[i]}_0", numeros[i], f"{numeros[i]}_1"])
            if i < 7:
                linhas.extend([f"L{l_count}"])
                l_count += 1
        linhas.extend(['Bot0', 'Bot1', 'Bot2'])
        
        matriz_base = np.full((37, 37), '.', dtype='<U4')
        return pd.DataFrame(matriz_base, index=linhas, columns=colunas)


    def erase_piece(self, position):
        """Remove uma peça e seus marcadores '#' ao redor de uma posição (UCI ou coordenada)."""
        x, y = position
        if isinstance(x, str):
            x_idx = self.grid.columns.get_loc(x)
            y_idx = self.grid.index.get_loc(y)
        else:
            x_idx, y_idx = x, y
        
        for i in range(-1, 2):
            for j in range(-1, 2):
                if 0 <= y_idx + i < 37 and 0 <= x_idx + j < 37:
                    self.grid.iat[y_idx + i, x_idx + j] = '.'
        return self.grid

    def draw_piece(self, position, piece, with_markers=True):
        """Desenha uma peça e opcionalmente marcadores '#' ao redor em uma posição específica."""
        x, y = position
        if isinstance(x, str):
            x_idx = self.grid.columns.get_loc(x)
            y_idx = self.grid.index.get_loc(y)
        else:
            x_idx, y_idx = x, y
            
        if not with_markers:
            if 0 <= y_idx < 37 and 0 <= x_idx < 37:
                self.grid.iat[y_idx, x_idx] = piece
            return self.grid

        for i in range(-1, 2):
            for j in range(-1, 2):
                if 0 <= y_idx + i < 37 and 0 <= x_idx + j < 37:
                    if i == 0 and j == 0:
                        self.grid.iat[y_idx + i, x_idx + j] = piece
                    else:
                        self.grid.iat[y_idx + i, x_idx + j] = '#'
        return self.grid

    def preencher_por_fen(self, fen):
        """Preenche o tabuleiro baseado em uma string FEN."""
        self.grid[:] = "."
        
        posicao = fen.split(' ')[0]
        linhas_fen = posicao.split('/')
        
        for nu_linha, l in enumerate(linhas_fen):
            nu_colum = 0
            novo_l_idx = (4 * nu_linha) + 4
            for c in l:
                if c.isdigit():
                    nu_colum += int(c)
                else:
                    novo_c_idx = (4 * nu_colum) + 4
                    self.draw_piece([novo_c_idx, novo_l_idx], c)
                    nu_colum += 1
        return self.grid

    def get_storage_position(self, piece):
        """
        Calcula a próxima posição disponível nas colunas laterais para uma peça capturada.
        - Peças brancas (maiúsculas) vão para a lateral esquerda (E0), de baixo para cima.
        - Peças pretas (minúsculas) vão para a lateral direita (D2), de cima para baixo.
        Ocupam 3x3 (peça + markers) e mantêm 1 linha de distância entre si.
        """
        is_white = piece.isupper()
        col = self.STORAGE_COL_E if is_white else self.STORAGE_COL_D
        pos_count = self.capturadas_brancas_pos if is_white else self.capturadas_pretas_pos
        
        # Cada peça + markers ocupa 3 linhas. Para 1 linha de gap, o centro pula 4.
        if is_white:
            # Brancas: Começa em 33 (1_1). Markers em 32, 33, 34. 35 (Bot1) é restrito.
            row_idx = 33 - (pos_count * 4)
            self.capturadas_brancas_pos += 1
        else:
            # Pretas: Começa em 3 (8_0). Markers em 2, 3, 4. 1 (Top1) é restrito.
            row_idx = 3 + (pos_count * 4)
            self.capturadas_pretas_pos += 1
        
        if row_idx < 0: row_idx = 0
        if row_idx >= 37: row_idx = 36
            
        row_label = self.grid.index[row_idx]
        return [col, row_label]

    def __str__(self):
        return self.grid.to_string()

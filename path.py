import numpy as np
from pathfinding.core.diagonal_movement import DiagonalMovement
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder


class TurnPenalizingAStarFinder(AStarFinder):
    """
    Subclasse do AStarFinder que adiciona uma penalidade de custo ao realizar
    curvas (mudanças de direção), forçando caminhos mais retos.
    """

    def __init__(self, turn_penalty=5.0, **kwargs):
        super().__init__(**kwargs)
        self.turn_penalty = turn_penalty

    def process_node(self, graph, node, parent, end, open_list, open_value=True):
        # Custo básico de mover do pai para o vizinho
        base_cost = graph.calc_cost(parent, node, self.weighted)

        # Vetor de direção do movimento atual
        dx = node.x - parent.x
        dy = node.y - parent.y

        penalty = 0.0
        # Se o nó pai também tem um pai, podemos comparar as direções para detectar curvas
        if parent.parent:
            p_dx = parent.x - parent.parent.x
            p_dy = parent.y - parent.parent.y

            # Checa se são colineares e apontam no mesmo sentido
            # (produto vetorial zero e produto escalar >= 0 para ambas as componentes)
            is_collinear = (
                (dx * p_dy - dy * p_dx == 0) and (dx * p_dx >= 0) and (dy * p_dy >= 0)
            )
            if not is_collinear:
                penalty = self.turn_penalty

        ng = parent.g + base_cost + penalty

        if not node.opened or ng < node.g:
            old_f = node.f
            node.g = ng
            node.h = node.h or self.apply_heuristic(node, end, graph=graph)
            # f é o custo total estimado do início ao objetivo
            node.f = node.g + node.h
            node.parent = parent
            if not node.opened:
                open_list.push_node(node)
                node.opened = open_value
            else:
                # O nó pode ser alcançado com custo menor. Atualiza na lista aberta.
                open_list.push_node(node)


class PathPlanner:
    """
    Responsável por calcular rotas A* no tabuleiro e otimizar as trajetórias
    para o envio ao hardware (Arduino).
    """

    def __init__(
        self,
        diagonal_movement=DiagonalMovement.never,
        turn_penalty=5.0,
    ):
        self.diagonal_movement = diagonal_movement
        self.turn_penalty = turn_penalty
        self.finder = TurnPenalizingAStarFinder(
            turn_penalty=self.turn_penalty, diagonal_movement=self.diagonal_movement
        )

    def calcular_rota(self, board_df, inicio, fim):
        """
        Calcula a rota A* entre duas coordenadas.
        inicio/fim podem ser [x, y] numéricos ou [col_label, row_label].
        """
        matriz_str = board_df.to_numpy()

        # Onde for '.' vira 1 (Livre), o resto vira 0 (Obstáculo)
        matriz_binaria = np.where(matriz_str == ".", 1, 0).tolist()

        # Converte labels para índices se necessário
        if isinstance(inicio[0], str):
            x_ini = board_df.columns.get_loc(inicio[0])
            y_ini = board_df.index.get_loc(inicio[1])
            x_fim = board_df.columns.get_loc(fim[0])
            y_fim = board_df.index.get_loc(fim[1])
        else:
            x_ini, y_ini = inicio
            x_fim, y_fim = fim

        # Garante que início e fim estão livres na matriz binária para o A* funcionar
        matriz_binaria[y_ini][x_ini] = 1
        matriz_binaria[y_fim][x_fim] = 1

        grid = Grid(matrix=matriz_binaria)
        start_node = grid.node(x_ini, y_ini)
        end_node = grid.node(x_fim, y_fim)

        caminho, _ = self.finder.find_path(start_node, end_node, grid)
        return caminho

    def otimizar_trajetoria(self, caminho):
        """
        Remove pontos colineares da trajetória, retornando apenas os vértices
        onde há mudança de direção (curvas).
        """
        if len(caminho) <= 2:
            return caminho

        caminho_otimizado = [caminho[0]]

        for i in range(1, len(caminho) - 1):
            p1 = caminho_otimizado[-1]
            p2 = caminho[i]
            p3 = caminho[i + 1]

            ux, uy = p2.x - p1.x, p2.y - p1.y
            vx, vy = p3.x - p2.x, p3.y - p2.y

            # Produto vetorial 
            if (ux * vy) - (uy * vx) != 0:
                caminho_otimizado.append(p2)

        caminho_otimizado.append(caminho[-1])
        return caminho_otimizado

    def visualizar_rota(self, board_df, caminho):
        """Retorna uma cópia do DataFrame do tabuleiro com a rota marcada por '*'."""
        tab_visual = board_df.copy()
        linhas = tab_visual.index.tolist()
        colunas = tab_visual.columns.tolist()

        for node in caminho:
            row_label = linhas[node.y]
            col_label = colunas[node.x]
            if tab_visual.at[row_label, col_label] == ".":
                tab_visual.at[row_label, col_label] = "*"
        return tab_visual

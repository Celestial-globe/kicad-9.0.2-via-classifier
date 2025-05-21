#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VIA分類プラグイン（矩形対応版）
基板の外形線を基準にVIAを内側/外側/重複に分類します
矩形ツールで作成された外形線にも対応
"""

import pcbnew
import os
import wx
import math
import traceback  # デバッグ情報用

class ViaClassifierPlugin(pcbnew.ActionPlugin):
    def __init__(self):
        super().__init__()
        self.name = "Via分類ツール"
        self.category = "基板編集"
        self.description = "基板外形線を基準にVIAを内側/外側/重複に分類します"
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'via_classifier.png')
        
    def defaults(self):
        """プラグインのデフォルト設定"""
        self.name = "Via分類ツール"
        self.category = "基板編集"
        self.description = "基板外形線を基準にVIAを内側/外側/重複に分類します"
        self.show_toolbar_button = True
        
    def Run(self):
        """メイン実行関数"""
        try:  # 全体をtry-exceptで囲む
            board = pcbnew.GetBoard()
            
            # 選択されたVIAの数をカウント
            selected_vias_count = sum(1 for track in board.Tracks() if track.Type() == pcbnew.PCB_VIA_T and track.IsSelected())
            
            # 進捗ダイアログを表示
            progress_dialog = wx.ProgressDialog("処理中", "基板の外形線を解析中...", 
                                              maximum=100, parent=None, 
                                              style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
            progress_dialog.Update(10)
            
            # デバッグ情報収集開始
            debug_info = "デバッグ情報:\n"
            
            # 基板の外形線を取得
            try:
                # デバッグを有効にした外形線取得
                edge_points, debug_edge_info = self.get_board_outline_debug(board)
                debug_info += debug_edge_info
                
                if not edge_points:
                    # デバッグ情報を含むエラーメッセージ
                    progress_dialog.Destroy()
                    self.show_debug_dialog("外形線が見つからないエラー", debug_info + 
                                        "基板の外形線が見つかりませんでした。Edge.Cutsレイヤーに正しく外形線が作成されているか確認してください。")
                    return
            except Exception as e:
                progress_dialog.Destroy()
                error_trace = traceback.format_exc()
                self.show_debug_dialog("外形線処理エラー", debug_info + 
                                    f"基板外形線の処理中にエラーが発生しました:\n{str(e)}\n\n{error_trace}")
                return
                
            progress_dialog.Update(30, "VIAを分類中...")
            
            # 初期分類（デフォルトは選択されたVIAのみ、選択がない場合は基板全体）
            use_selection_only = selected_vias_count > 0
            try:
                inside_vias, outside_vias, overlap_vias = self.classify_vias(board, edge_points, use_selection_only)
                debug_info += f"VIAの分類結果: 内側={len(inside_vias)}個, 外側={len(outside_vias)}個, 重複={len(overlap_vias)}個\n"
            except Exception as e:
                progress_dialog.Destroy()
                error_trace = traceback.format_exc()
                self.show_debug_dialog("VIA分類エラー", debug_info + 
                                    f"VIAの分類中にエラーが発生しました:\n{str(e)}\n\n{error_trace}")
                return
            
            progress_dialog.Update(80, "結果を準備中...")
            progress_dialog.Destroy()
            
            # 統合ダイアログを表示
            self.show_unified_dialog(board, inside_vias, outside_vias, overlap_vias, selected_vias_count, edge_points, debug_info)
            
        except Exception as e:
            # 全体的な例外をキャッチ
            error_trace = traceback.format_exc()
            try:
                progress_dialog.Destroy()
            except:
                pass
            self.show_debug_dialog("予期せぬエラー", f"プラグインの実行中に予期せぬエラーが発生しました:\n{str(e)}\n\n{error_trace}")
    
    def show_debug_dialog(self, title, message):
        """デバッグ情報を表示するダイアログ"""
        dlg = wx.Dialog(None, title=title, size=(600, 400))
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # スクロール可能なテキストコントロール
        text_ctrl = wx.TextCtrl(dlg, value=message, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        vbox.Add(text_ctrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=10)
        
        # 閉じるボタン
        btn_close = wx.Button(dlg, wx.ID_CLOSE, "閉じる")
        vbox.Add(btn_close, flag=wx.ALIGN_CENTER | wx.ALL, border=10)
        
        btn_close.Bind(wx.EVT_BUTTON, lambda evt: dlg.EndModal(wx.ID_CLOSE))
        
        dlg.SetSizer(vbox)
        dlg.ShowModal()
        dlg.Destroy()
        
    def get_board_outline_debug(self, board):
        """基板の外形線データを点のリストとして取得し、デバッグ情報も返す"""
        edge_cut_layer = pcbnew.Edge_Cuts
        segments = []
        debug_info = ""
        
        # Edge.Cutsレイヤーの要素をカウント
        edge_count = sum(1 for drawing in board.GetDrawings() if drawing.GetLayer() == edge_cut_layer)
        debug_info += f"Edge.Cutsレイヤーの要素数: {edge_count}個\n"
        
        # すべての図形要素を収集
        for drawing in board.GetDrawings():
            if drawing.GetLayer() == edge_cut_layer:
                shape_type = drawing.GetShape()
                
                # 線分
                if shape_type == pcbnew.S_SEGMENT:
                    start = drawing.GetStart()
                    end = drawing.GetEnd()
                    segments.append((start, end))
                
                # 弧
                elif shape_type == pcbnew.S_ARC:
                    start = drawing.GetStart()
                    end = drawing.GetEnd()
                    center = drawing.GetCenter()
                    
                    radius = math.sqrt((start.x - center.x)**2 + (start.y - center.y)**2)
                    start_angle = math.atan2(start.y - center.y, start.x - center.x)
                    end_angle = math.atan2(end.y - center.y, end.x - center.x)
                    if start_angle < 0:
                        start_angle += 2 * math.pi
                    if end_angle < 0:
                        end_angle += 2 * math.pi
                    
                    # KiCadの弧は常に反時計回り
                    if end_angle <= start_angle:
                        end_angle += 2 * math.pi
                    
                    angle_step = math.radians(5)  # より小さなステップでより正確に
                    segment_count = abs(int((end_angle - start_angle) / angle_step)) + 1
                    current_angle = start_angle
                    last_point = start
                    
                    for i in range(segment_count):
                        next_angle = current_angle + angle_step
                        if next_angle > end_angle:
                            next_angle = end_angle
                        x = center.x + int(radius * math.cos(next_angle))
                        y = center.y + int(radius * math.sin(next_angle))
                        next_point = pcbnew.VECTOR2I(x, y)
                        segments.append((last_point, next_point))
                        last_point = next_point
                        current_angle = next_angle
                        if next_angle >= end_angle:
                            break
                
                # 円
                elif shape_type == pcbnew.S_CIRCLE:
                    center = drawing.GetCenter()
                    radius = drawing.GetRadius()
                    
                    # 円を分割して線分として扱う（24分割）
                    angle_step = 2 * math.pi / 24
                    for i in range(24):
                        angle1 = i * angle_step
                        angle2 = (i + 1) * angle_step
                        x1 = center.x + int(radius * math.cos(angle1))
                        y1 = center.y + int(radius * math.sin(angle1))
                        x2 = center.x + int(radius * math.cos(angle2))
                        y2 = center.y + int(radius * math.sin(angle2))
                        start_point = pcbnew.VECTOR2I(x1, y1)
                        end_point = pcbnew.VECTOR2I(x2, y2)
                        segments.append((start_point, end_point))
                
                # 矩形（重要な追加）
                elif shape_type == pcbnew.S_RECT:
                    # 矩形の4つの角の座標を取得
                    rect_start = drawing.GetStart()
                    rect_end = drawing.GetEnd()
                    
                    # 4つの頂点を計算
                    x1, y1 = rect_start.x, rect_start.y
                    x2, y2 = rect_end.x, rect_end.y
                    
                    # 矩形の4つの辺を追加
                    segments.append((pcbnew.VECTOR2I(x1, y1), pcbnew.VECTOR2I(x2, y1)))  # 上辺
                    segments.append((pcbnew.VECTOR2I(x2, y1), pcbnew.VECTOR2I(x2, y2)))  # 右辺
                    segments.append((pcbnew.VECTOR2I(x2, y2), pcbnew.VECTOR2I(x1, y2)))  # 下辺
                    segments.append((pcbnew.VECTOR2I(x1, y2), pcbnew.VECTOR2I(x1, y1)))  # 左辺
                
                # ポリゴン
                elif shape_type == pcbnew.S_POLYGON:
                    try:
                        # ポリゴンの頂点を取得
                        outline = drawing.GetPolyShape().Outline(0)
                        point_count = outline.PointCount()
                        
                        # ポリゴンの各辺を追加
                        for i in range(point_count):
                            start_point = outline.CPoint(i)
                            end_point = outline.CPoint((i + 1) % point_count)
                            segments.append((start_point, end_point))
                    except Exception as e:
                        debug_info += f"ポリゴン処理エラー: {str(e)}\n"
                
                # その他の形状
                else:
                    debug_info += f"未対応の形状タイプ: {shape_type}\n"
        
        debug_info += f"検出されたセグメント数: {len(segments)}個\n"
        
        if not segments:
            debug_info += "セグメントが検出されませんでした。\n"
            return [], debug_info
            
        # セグメントを連結して順序付き点のリストを作成
        ordered_points = self.connect_segments_improved(segments)
        debug_info += f"連結後の点の数: {len(ordered_points)}個\n"
        
        # 接続が成功したかチェック
        if len(ordered_points) <= 1:
            debug_info += "セグメントの連結に失敗しました。\n"
            return [], debug_info
        
        # 仮想的なフィレットを適用（0.1mm = 100,000 KiCadユニット）
        filleted_points = self.apply_virtual_fillets(ordered_points, 100000)
        
        return filleted_points, debug_info

    def connect_segments_improved(self, segments):
        """改良版：セグメントを連結して順序付き点のリストを作成"""
        if not segments:
            return []

        # すべてのユニークな点を抽出（セグメントの端点）
        all_points = []
        for start, end in segments:
            all_points.append((start.x, start.y))
            all_points.append((end.x, end.y))
        
        # 重複を削除
        unique_points = []
        for point in all_points:
            is_unique = True
            for existing in unique_points:
                if abs(point[0] - existing[0]) < 10000 and abs(point[1] - existing[1]) < 10000:
                    is_unique = False
                    break
            if is_unique:
                unique_points.append(point)
        
        # 点が少なすぎる場合は失敗
        if len(unique_points) < 3:
            return []
        
        # 輪郭を形成する順序で点を整列
        # 最も左上の点から開始
        start_point = min(unique_points, key=lambda p: (p[0], p[1]))
        ordered_points = [start_point]
        remaining_points = [p for p in unique_points if p != start_point]
        
        # 最も近い点を常に次に選ぶ（時計回りまたは反時計回り）
        while remaining_points:
            current = ordered_points[-1]
            
            # 現在の点から最も近い点を選ぶ
            closest = min(remaining_points, key=lambda p: (p[0] - current[0])**2 + (p[1] - current[1])**2)
            ordered_points.append(closest)
            remaining_points.remove(closest)
            
            # もし残りの点が1つだけで、それが開始点に近ければ、ループを閉じる
            if len(remaining_points) == 1:
                last_point = remaining_points[0]
                first_point = ordered_points[0]
                if (last_point[0] - first_point[0])**2 + (last_point[1] - first_point[1])**2 < 100000000:
                    ordered_points.append(last_point)
                    break
        
        # 単純なアルゴリズムがうまくいかない場合は、別のアプローチを試す
        # 最初の点から時計回りに整列
        if len(ordered_points) < len(unique_points) / 2:
            # 最も左上の点を見つける
            leftmost = min(unique_points, key=lambda p: p[0])
            center_x = sum(p[0] for p in unique_points) / len(unique_points)
            center_y = sum(p[1] for p in unique_points) / len(unique_points)
            
            # 中心からの角度でソート
            def angle_from_center(point):
                return math.atan2(point[1] - center_y, point[0] - center_x)
                
            ordered_points = sorted(unique_points, key=angle_from_center)
        
        # KiCadのVECTOR2Iオブジェクトに変換
        result_points = [pcbnew.VECTOR2I(int(x), int(y)) for x, y in ordered_points]
        
        # 最初と最後の点が同じでない場合は閉じる
        if len(result_points) > 1 and not self.points_are_close(result_points[0], result_points[-1]):
            result_points.append(result_points[0])
        
        return result_points

    def apply_virtual_fillets(self, points, fillet_radius=100000):
        """直角部分に仮想的なフィレットを適用（0.1mm = 100,000 KiCadユニット）"""
        if len(points) < 3:
            return points
        
        result_points = []
        result_points.append(points[0])  # 最初の点を追加
        
        # 中間の点を処理
        for i in range(1, len(points) - 1):
            prev_point = points[i - 1]
            current_point = points[i]
            next_point = points[i + 1]
            
            # 2つのベクトルを計算
            v1x = current_point.x - prev_point.x
            v1y = current_point.y - prev_point.y
            v2x = next_point.x - current_point.x
            v2y = next_point.y - current_point.y
            
            # ベクトルの長さを計算
            v1_len = math.sqrt(v1x**2 + v1y**2)
            v2_len = math.sqrt(v2x**2 + v2y**2)
            
            if v1_len < 1 or v2_len < 1:
                result_points.append(current_point)
                continue
            
            # 正規化
            v1x /= v1_len
            v1y /= v1_len
            v2x /= v2_len
            v2y /= v2_len
            
            # 内積を計算（角度のコサイン）
            dot_product = v1x * v2x + v1y * v2y
            
            # 直角またはほぼ直角かどうかチェック（cos(90°) = 0）
            if abs(dot_product) < 0.2:  # ほぼ直角と見なす閾値
                # フィレット半径をベクトル方向に適用（短い方の辺の長さの半分以下に制限）
                radius = min(fillet_radius, v1_len / 2, v2_len / 2)
                
                # フィレット点の計算
                p1 = pcbnew.VECTOR2I(
                    int(current_point.x - v1x * radius),
                    int(current_point.y - v1y * radius)
                )
                
                p3 = pcbnew.VECTOR2I(
                    int(current_point.x + v2x * radius),
                    int(current_point.y + v2y * radius)
                )
                
                # 結果に追加
                result_points.append(p1)
                
                # 円弧を近似する中間点（オプション）
                arc_steps = 2  # 円弧の近似点数
                for step in range(1, arc_steps + 1):
                    t = step / (arc_steps + 1)
                    # 簡易ベジェ曲線で円弧を近似
                    px = (1-t)**2 * p1.x + 2*(1-t)*t * current_point.x + t**2 * p3.x
                    py = (1-t)**2 * p1.y + 2*(1-t)*t * current_point.y + t**2 * p3.y
                    arc_point = pcbnew.VECTOR2I(int(px), int(py))
                    result_points.append(arc_point)
                
                result_points.append(p3)
            else:
                # 直角でない場合はそのまま追加
                result_points.append(current_point)
        
        if len(points) > 1:
            result_points.append(points[-1])  # 最後の点を追加
        
        # 開始点と終了点が異なる場合は閉じる
        if len(result_points) > 1 and not self.points_are_close(result_points[0], result_points[-1]):
            result_points.append(result_points[0])
        
        return result_points

    def points_are_close(self, p1, p2, tolerance=10000):
        """2点が近いか判定"""
        return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2) < tolerance

    def point_in_polygon(self, point, polygon):
        """点が多角形の内側にあるかを判定（レイキャスティング法）"""
        if not polygon or len(polygon) < 3:
            return False
        x, y = point.x, point.y
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0].x, polygon[0].y
        for i in range(n + 1):
            p2x, p2y = polygon[i % n].x, polygon[i % n].y
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside

    def distance_to_segment(self, point, segment_start, segment_end):
        """点から線分までの最短距離を計算"""
        x, y = point.x, point.y
        x1, y1 = segment_start.x, segment_start.y
        x2, y2 = segment_end.x, segment_end.y
        A = x - x1
        B = y - y1
        C = x2 - x1
        D = y2 - y1
        dot = A * C + B * D
        len_sq = C * C + D * D
        if len_sq == 0:
            return math.sqrt(A * A + B * B)
        param = dot / len_sq
        if param < 0:
            xx = x1
            yy = y1
        elif param > 1:
            xx = x2
            yy = y2
        else:
            xx = x1 + param * C
            yy = y1 + param * D
        return math.sqrt((x - xx) ** 2 + (y - yy) ** 2)

    def classify_vias(self, board, outline_points, selected_only=False):
        """VIAを内側/外側/重複に分類"""
        inside_vias, outside_vias, overlap_vias = [], [], []
        if not outline_points or len(outline_points) < 3:
            return [], [], []
        
        vias = [track for track in board.Tracks() if track.Type() == pcbnew.PCB_VIA_T and (not selected_only or track.IsSelected())]
        
        if selected_only and not vias:
            wx.MessageBox("選択されたVIAが見つかりませんでした。", "警告", wx.ICON_WARNING)
            return [], [], []
        
        for via in vias:
            position = via.GetPosition()
            via_diameter = via.GetWidth()
            via_radius = via_diameter // 2
            is_inside = self.point_in_polygon(position, outline_points)
            is_overlapping = False
            
            for i in range(len(outline_points) - 1):
                start_point = outline_points[i]
                end_point = outline_points[i + 1]
                dist = self.distance_to_segment(position, start_point, end_point)
                if dist <= via_radius:
                    is_overlapping = True
                    break
            
            if is_overlapping:
                overlap_vias.append(via)
            elif is_inside:
                inside_vias.append(via)
            else:
                outside_vias.append(via)
        
        return inside_vias, outside_vias, overlap_vias

    def show_unified_dialog(self, board, inside_vias, outside_vias, overlap_vias, selected_vias_count, edge_points, debug_info=""):
        """処理範囲の選択と結果表示を統合したダイアログ"""
        dialog = wx.Dialog(None, title="VIA分類ツール", size=(480, 500))
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # 処理範囲の選択
        scope_label = wx.StaticText(dialog, label="処理範囲の選択:")
        font = scope_label.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        scope_label.SetFont(font)
        vbox.Add(scope_label, flag=wx.ALL, border=10)
        
        scope_box = wx.BoxSizer(wx.HORIZONTAL)
        scope_choice = wx.Choice(dialog, choices=[f"選択されたVIAのみ ({selected_vias_count}個)", "基板全体を処理"])
        scope_choice.SetSelection(0 if selected_vias_count > 0 else 1)  # デフォルトを選択されたVIAに
        scope_box.Add(scope_choice, flag=wx.LEFT|wx.RIGHT, border=20)
        vbox.Add(scope_box, flag=wx.EXPAND|wx.ALL, border=5)
        
        # 結果表示
        result_label = wx.StaticText(dialog, label="分類結果:")
        result_label.SetFont(font)
        vbox.Add(result_label, flag=wx.ALL, border=10)
        
        results_box = wx.BoxSizer(wx.VERTICAL)
        total_vias = len(inside_vias) + len(outside_vias) + len(overlap_vias)
        inside_text = wx.StaticText(dialog, label=f"内側のVIA: {len(inside_vias)}個")
        outside_text = wx.StaticText(dialog, label=f"外側のVIA: {len(outside_vias)}個")
        overlap_text = wx.StaticText(dialog, label=f"外形線と重複するVIA: {len(overlap_vias)}個")
        total_text = wx.StaticText(dialog, label=f"合計: {total_vias}個のVIA")
        results_box.Add(inside_text, flag=wx.LEFT, border=20)
        results_box.Add(outside_text, flag=wx.LEFT, border=20)
        results_box.Add(overlap_text, flag=wx.LEFT, border=20)
        results_box.Add(total_text, flag=wx.LEFT, border=20)
        vbox.Add(results_box, flag=wx.EXPAND|wx.ALL, border=5)
        
        # 削除オプション
        delete_label = wx.StaticText(dialog, label="削除するVIAを選択:")
        delete_label.SetFont(font)
        vbox.Add(delete_label, flag=wx.ALL, border=10)
        
        delete_box = wx.BoxSizer(wx.VERTICAL)
        chk_inside = wx.CheckBox(dialog, label=f"内側のVIA ({len(inside_vias)}個)")
        chk_outside = wx.CheckBox(dialog, label=f"外側のVIA ({len(outside_vias)}個)")
        chk_overlap = wx.CheckBox(dialog, label=f"重複するVIA ({len(overlap_vias)}個)")
        delete_box.Add(chk_inside, flag=wx.LEFT, border=20)
        delete_box.Add(chk_outside, flag=wx.LEFT, border=20)
        delete_box.Add(chk_overlap, flag=wx.LEFT, border=20)
        vbox.Add(delete_box, flag=wx.EXPAND|wx.ALL, border=5)
        
        # 削除警告
        delete_warning = wx.StaticText(dialog, label="※削除操作は元に戻せません")
        delete_warning.SetForegroundColour(wx.RED)
        vbox.Add(delete_warning, flag=wx.EXPAND|wx.LEFT|wx.TOP, border=20)
        
        # デバッグ情報ボタン
        debug_btn = wx.Button(dialog, label="診断情報を表示")
        vbox.Add(debug_btn, flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        debug_btn.Bind(wx.EVT_BUTTON, lambda evt: self.show_debug_dialog("診断情報", debug_info))
        
        # ボタン
        btn_box = wx.BoxSizer(wx.HORIZONTAL)
        btn_delete = wx.Button(dialog, label="選択したVIAを削除")
        btn_delete.SetForegroundColour(wx.RED)
        btn_close = wx.Button(dialog, wx.ID_CLOSE, "閉じる")
        btn_box.Add(btn_delete, flag=wx.RIGHT, border=5)
        btn_box.Add(btn_close, flag=wx.RIGHT, border=5)
        vbox.Add(btn_box, flag=wx.ALIGN_CENTER|wx.ALL, border=10)
        
        # 処理範囲変更時の再分類
        def on_scope_change(evt):
            use_selection_only = scope_choice.GetSelection() == 0
            inside_vias_new, outside_vias_new, overlap_vias_new = self.classify_vias(board, edge_points, use_selection_only)
            inside_vias[:] = inside_vias_new
            outside_vias[:] = outside_vias_new
            overlap_vias[:] = overlap_vias_new
            total_vias_new = len(inside_vias) + len(outside_vias) + len(overlap_vias)
            inside_text.SetLabel(f"内側のVIA: {len(inside_vias)}個")
            outside_text.SetLabel(f"外側のVIA: {len(outside_vias)}個")
            overlap_text.SetLabel(f"外形線と重複するVIA: {len(overlap_vias)}個")
            total_text.SetLabel(f"合計: {total_vias_new}個のVIA")
            chk_inside.SetLabel(f"内側のVIA ({len(inside_vias)}個)")
            chk_outside.SetLabel(f"外側のVIA ({len(outside_vias)}個)")
            chk_overlap.SetLabel(f"重複するVIA ({len(overlap_vias)}個)")
            dialog.Layout()
        
        scope_choice.Bind(wx.EVT_CHOICE, on_scope_change)
        btn_delete.Bind(wx.EVT_BUTTON, lambda evt: self.delete_selected_vias(
            board, 
            inside_vias if chk_inside.GetValue() else [], 
            outside_vias if chk_outside.GetValue() else [], 
            overlap_vias if chk_overlap.GetValue() else []
        ))
        btn_close.Bind(wx.EVT_BUTTON, lambda evt: dialog.EndModal(wx.ID_CLOSE))
        
        dialog.SetSizer(vbox)
        dialog.Fit()
        dialog.ShowModal()
        dialog.Destroy()

    def delete_selected_vias(self, board, inside_vias, outside_vias, overlap_vias):
        """チェックボックスで選択されたVIAを削除"""
        all_selected_vias = []
        all_selected_vias.extend(inside_vias)
        all_selected_vias.extend(outside_vias)
        all_selected_vias.extend(overlap_vias)
        
        if not all_selected_vias:
            wx.MessageBox("削除するVIAが選択されていません。", "情報", wx.ICON_INFORMATION)
            return
        
        info_str = ""
        if inside_vias:
            info_str += f"内側: {len(inside_vias)}個 "
        if outside_vias:
            info_str += f"外側: {len(outside_vias)}個 "
        if overlap_vias:
            info_str += f"重複: {len(overlap_vias)}個 "
            
        dlg = wx.MessageDialog(None, 
                              f"選択された{len(all_selected_vias)}個のVIA ({info_str})を削除しますか？\nこの操作は元に戻せません。",
                              "削除の確認",
                              wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
        
        if dlg.ShowModal() == wx.ID_YES:
            for via in all_selected_vias:
                board.Remove(via)
            pcbnew.Refresh()
            wx.MessageBox(f"{len(all_selected_vias)}個のVIAが削除されました。", "削除完了", wx.ICON_INFORMATION)
        
        dlg.Destroy()

# プラグインを登録
ViaClassifierPlugin().register()
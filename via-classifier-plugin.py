#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
VIA分類プラグイン
基板の外形線を基準にVIAを内側/外側/重複に分類します
"""

import pcbnew
import os
import wx
import math

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
        board = pcbnew.GetBoard()
        
        # 選択されたVIAの数をカウント
        selected_vias_count = sum(1 for track in board.Tracks() if track.Type() == pcbnew.PCB_VIA_T and track.IsSelected())
        
        # 進捗ダイアログを表示
        progress_dialog = wx.ProgressDialog("処理中", "基板の外形線を解析中...", 
                                          maximum=100, parent=None, 
                                          style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
        progress_dialog.Update(10)
        
        # 基板の外形線を取得
        try:
            edge_points = self.get_board_outline(board)
            if not edge_points:
                wx.MessageBox("基板の外形線が見つかりませんでした。Edge.Cutsレイヤーに正しく外形線が作成されているか確認してください。", 
                            "エラー", wx.ICON_ERROR)
                progress_dialog.Destroy()
                return
        except Exception as e:
            wx.MessageBox(f"基板外形線の処理中にエラーが発生しました: {str(e)}", 
                        "エラー", wx.ICON_ERROR)
            progress_dialog.Destroy()
            return
            
        progress_dialog.Update(30, "VIAを分類中...")
        
        # 初期分類（デフォルトは選択されたVIAのみ、選択がない場合は基板全体）
        use_selection_only = selected_vias_count > 0
        try:
            inside_vias, outside_vias, overlap_vias = self.classify_vias(board, edge_points, use_selection_only)
        except Exception as e:
            wx.MessageBox(f"VIAの分類中にエラーが発生しました: {str(e)}", 
                        "エラー", wx.ICON_ERROR)
            progress_dialog.Destroy()
            return
        
        progress_dialog.Update(80, "結果を準備中...")
        progress_dialog.Destroy()
        
        # 統合ダイアログを表示
        self.show_unified_dialog(board, inside_vias, outside_vias, overlap_vias, selected_vias_count, edge_points)
        
def points_are_close(self, p1, p2, tolerance=1000):  # 許容誤差を0.001mmに縮小
    """2点が近いか判定"""
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2) < tolerance

def get_board_outline(self, board):
    """基板の外形線データを点のリストとして取得"""
    edge_cut_layer = pcbnew.Edge_Cuts
    segments = []
    
    # 外形線のセグメントを取得
    for drawing in board.GetDrawings():
        if drawing.GetLayer() == edge_cut_layer:
            shape_type = drawing.GetShape()
            
            if shape_type == pcbnew.S_SEGMENT:
                start = drawing.GetStart()
                end = drawing.GetEnd()
                segments.append((start, end))
            
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
                clockwise = False
                angle_diff = end_angle - start_angle
                if not clockwise and angle_diff < 0:
                    angle_diff += 2 * math.pi
                angle_step = math.radians(10)
                segment_count = abs(int(angle_diff / angle_step)) + 1
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
                    if next_angle == end_angle:
                        break
            
            elif shape_type == pcbnew.S_CIRCLE:
                wx.MessageBox("警告: 円形の外形線要素が検出されました。この形状は現在サポートされていません。", 
                             "警告", wx.ICON_WARNING)
    
    if not segments:
        return []
    
    # セグメントを接続して閉じたパスを構築
    ordered_points = [segments[0][0]]
    used_segments = {0}
    current_point = segments[0][1]
    max_iterations = len(segments) * 2
    
    for _ in range(max_iterations):
        found = False
        for i, (start, end) in enumerate(segments):
            if i in used_segments:
                continue
            # 現在の点と次のセグメントの開始点または終了点が近いかを確認
            if self.points_are_close(current_point, start):
                used_segments.add(i)
                ordered_points.append(start)
                current_point = end
                found = True
                break
            elif self.points_are_close(current_point, end):
                used_segments.add(i)
                ordered_points.append(end)
                current_point = start
                found = True
                break
        
        if not found:
            # 接続が見つからない場合、近接する点を検索してマージ
            for i, (start, end) in enumerate(segments):
                if i in used_segments:
                    continue
                min_dist_start = self.distance_to_segment(current_point, start, end)
                min_dist_end = self.distance_to_segment(current_point, start, end)
                if min_dist_start < 1000 or min_dist_end < 1000:  # 近接するセグメントを強制接続
                    used_segments.add(i)
                    ordered_points.append(start)
                    current_point = end
                    found = True
                    break
        
        if not found or len(used_segments) == len(segments):
            break
    
    # 閉じたポリゴンを確認
    if ordered_points and not self.points_are_close(ordered_points[0], ordered_points[-1], tolerance=1000):
        # 最後の点と最初の点を強制的に接続
        ordered_points.append(ordered_points[0])
        wx.MessageBox("警告: 外形線が閉じていないため、強制的に閉じました。", 
                     "警告", wx.ICON_WARNING)
    
    # デバッグ: 取得したポイントをログに出力
    print("Ordered points:", [(p.x, p.y) for p in ordered_points])
    
    return ordered_points

    def points_are_close(self, p1, p2, tolerance=10000):
        """2点が近いか判定"""
        return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2) < tolerance

    def point_in_polygon(self, point, polygon):
        """点が多角形の内側にあるかを判定（レイキャスティング法）"""
        if not polygon:
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
        if not outline_points:
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
            
            for i in range(len(outline_points)):
                start_point = outline_points[i]
                end_point = outline_points[(i + 1) % len(outline_points)]
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

    def show_unified_dialog(self, board, inside_vias, outside_vias, overlap_vias, selected_vias_count, edge_points):
        """処理範囲の選択と結果表示を統合したダイアログ"""
        dialog = wx.Dialog(None, title="VIA分類ツール", size=(450, 400))
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
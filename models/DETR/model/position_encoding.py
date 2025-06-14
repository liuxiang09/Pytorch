import math
import torch
from torch import nn
from typing import Optional

# 导入NestedTensor
from DETR.utils.utils import NestedTensor

class PositionEmbeddingSine(nn.Module):
    """
    使用正弦位置编码来编码位置信息。
    Google gemini canvas 文档: https://gemini.google.com/share/8c880bebdc06
    """
    def __init__(self, num_pos_feats: int = 128, temperature: int = 10000, normalize: bool = False, scale: Optional[float] = None):
        super().__init__()
        self.num_pos_feats = num_pos_feats
        self.temperature = temperature
        self.normalize = normalize
        if scale is None:
            scale = 2 * math.pi
        self.scale = scale
        
    def forward(self, tensor: NestedTensor):
        """
        Args:
            tensor: NestedTensor对象，包含'tensor'和'mask'属性
        Returns:
            pos: [B, hidden_dim, H, W] 位置编码
        """
        mask = tensor.mask  # [B, H, W]，True表示padding
        not_mask = ~mask  # 反转mask，False表示padding位置
        y_embed = not_mask.cumsum(1, dtype=torch.float32)  # 累加得到y坐标
        x_embed = not_mask.cumsum(2, dtype=torch.float32)  # 累加得到x坐标
        
        if self.normalize:
            eps = 1e-6
            y_embed = y_embed / (y_embed[:, -1:, :] + eps) * self.scale  # 归一化
            x_embed = x_embed / (x_embed[:, :, -1:] + eps) * self.scale  # 归一化
        
        # 生成频率张量 
        dim_t = torch.arange(self.num_pos_feats, dtype=torch.float32, device=mask.device)  # [num_pos_feats]
        dim_t = self.temperature ** (2 * (dim_t // 2) / self.num_pos_feats)  # [num_pos_feats]
        
        # 广播机制，将维度扩展为[B, H, W, num_pos_feats]
        # x_embed 和 y_embed 的维度是[B, H, W]，dim_t 的维度是[num_pos_feats]
        pos_x = x_embed[:, :, :, None] / dim_t
        pos_y = y_embed[:, :, :, None] / dim_t
        
        pos_x = torch.stack((pos_x[:, :, :, 0::2].sin(), pos_x[:, :, :, 1::2].cos()), dim=4).flatten(3) # stack + flatten 实现交错排列
        pos_y = torch.stack((pos_y[:, :, :, 0::2].sin(), pos_y[:, :, :, 1::2].cos()), dim=4).flatten(3)
        
        pos = torch.cat((pos_y, pos_x), dim=3).permute(0, 3, 1, 2)
        return pos


class PositionEmbeddingLearned(nn.Module):
    """
    可学习的位置编码。
    Google gemini canvas 文档: https://gemini.google.com/share/6d99e5178acd
    """
    def __init__(self, num_pos_feats: int = 128):
        super().__init__()
        # 创建两个查询表，一个给行（高度），一个给列（宽度）
        # 50是一个预设的最大值，表示模型能处理的最大高/宽
        self.row_embed = nn.Embedding(50, num_pos_feats)
        self.col_embed = nn.Embedding(50, num_pos_feats)
        self.reset_parameters()

    def reset_parameters(self):
        # 用均匀分布初始化查询表里的权重
        nn.init.uniform_(self.row_embed.weight)
        nn.init.uniform_(self.col_embed.weight)

    def forward(self, mask):
        h, w = mask.shape[-2:]
        i = torch.arange(w, device=mask.device) # 列索引: [0, 1, ..., w-1]
        j = torch.arange(h, device=mask.device) # 行索引: [0, 1, ..., h-1]
        
        # 从查询表中查找每个行/列索引对应的向量
        x_emb = self.col_embed(i)  # [W, C]
        y_emb = self.row_embed(j)  # [H, C]
        
        # 将行、列向量组合成一个 [H, W, 2*C] 的位置图，然后调整维度
        pos = torch.cat([
            x_emb.unsqueeze(0).repeat(h, 1, 1), # [H, W, C]
            y_emb.unsqueeze(1).repeat(1, w, 1), # [H, W, C]
        ], dim=-1).permute(2, 0, 1).unsqueeze(0).repeat(mask.shape[0], 1, 1, 1)

        return pos



def build_position_encoding(args):
    """
    根据参数构建位置编码。
    
    Args:
        args: 包含position_embedding和hidden_dim的参数对象
    
    Returns:
        位置编码模块
    """
    N_steps = args.hidden_dim // 2
    
    if args.position_embedding in ('v2', 'sine'):
        # 使用正弦位置编码
        position_embedding = PositionEmbeddingSine(
            num_pos_feats=N_steps,
            normalize=True
        )
    elif args.position_embedding in ('v3', 'learned'):
        # 使用可学习的位置编码
        position_embedding = PositionEmbeddingLearned(
            num_pos_feats=N_steps
        )
    else:
        raise ValueError(f"不支持的位置编码类型: {args.position_embedding}")
    
    return position_embedding

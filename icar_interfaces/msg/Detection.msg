# Detection.msg — 单个检测目标
# 用于 DetectionArray 嵌套

string class_name           # 目标类别 (person/obstacle/water/sign/unknown)
float32 confidence          # 置信度 0.0-1.0
int32 x_min                 # 边界框左上 x
int32 y_min                 # 边界框左上 y
int32 x_max                 # 边界框右下 x
int32 y_max                 # 边界框右下 y
string image_path           # 截图保存路径

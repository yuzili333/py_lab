# 解析excel文件，获取该文件中每个sheet的内容
# 第一步获取本地指定路径的excel文件
# 第二步获取该excel文件中所有sheet的名称
import logging
import os

import pandas as pd

logger = logging.getLogger("analyze_excel")
logging.basicConfig(level=logging.INFO)

def analyze_excel(file_path: str) -> dict[str, list[list]]:
    """
    解析excel文件，获取该文件中每个sheet的内容

    参数:
    file_path (str): excel文件的路径

    返回:
    Dict[str, List[List]]: 包含每个sheet名称及其内容的字典
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"The file at {file_path} does not exist.")

    # 读取excel文件
    excel_data = pd.ExcelFile(file_path)

    # 获取所有sheet名称
    sheet_names = excel_data.sheet_names

    # 存储结果的字典
    result = {}

    # 遍历每个sheet，获取内容
    for sheet_name in sheet_names:
        df = pd.read_excel(excel_data, sheet_name=sheet_name)
        # 将DataFrame转换为二维列表
        sheet_content = df.values.tolist()
        result[sheet_name] = sheet_content

    logger.info(f"Successfully analyzed excel file: {file_path}")
    return result

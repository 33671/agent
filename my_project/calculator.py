"""简单的计算器模块"""

def add(a: float, b: float) -> float:
    """加法"""
    return a + b

def subtract(a: float, b: float) -> float:
    """减法"""
    return a - b

def multiply(a: float, b: float) -> float:
    """乘法"""
    return a * b

def divide(a: float, b: float) -> float:
    """除法"""
    if b == 0:
        raise ValueError("不能除以零")
    return a / b

if __name__ == "__main__":
    print("计算器测试:")
    print(f"10 + 5 = {add(10, 5)}")
    print(f"10 - 5 = {subtract(10, 5)}")
    print(f"10 * 5 = {multiply(10, 5)}")
    print(f"10 / 5 = {divide(10, 5)}")

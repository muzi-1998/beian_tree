# 环境策略

设计检查器仅依赖 Python 标准库，Python>=3.10。本轮使用现有 Python 3.10 环境运行 M01 与 M02 档案诊断，没有安装新包。numpy/pandas/pyarrow/matplotlib 的确切版本登记于 pyproject.toml 的 execution 可选依赖，并在每次运行的 environment.json 中记录实际版本。

实现时优先考虑numpy/pandas/scipy、statsmodels（ARMA/状态空间/MSTL）、scikit-learn（聚类）、pyarrow（Parquet）、openpyxl（图表源数据）。Vine实现库及其Python/平台兼容性需查官方文档并做小试后选择；当前不声明已可用。SUMO接口同样待本机版本与实际模型核实。

先记录现有环境，再在独立环境小试；成功后锁定确切版本与依赖哈希。不得为了骨架展示自动安装不兼容版本或把候选库写成已验证运行依赖。算法包不放入当前零依赖检查器的必装依赖。

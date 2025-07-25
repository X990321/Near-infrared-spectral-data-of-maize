import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, r2_score
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.signal import savgol_filter
import os
from tqdm import tqdm

# 设置随机种子，保证结果可复现
seed=2
torch.manual_seed(seed)
np.random.seed(seed)

# 设置中文字体，确保中文显示正常
plt.rcParams["font.family"] = ["SimHei", "WenQuanYi Micro Hei", "Heiti TC"]
plt.rcParams["axes.unicode_minus"] = False  # 确保负号显示正常

class NIRSpectroscopyDataset(Dataset):
    """近红外光谱数据集"""
    
    def __init__(self, spectra, targets, transform=None):
        """
        初始化数据集
        Args:
            spectra: 光谱数据
            targets: 目标成分含量数据
            transform: 数据转换操作
        """
        self.spectra = spectra
        self.targets = targets
        self.transform = transform
        
    def __len__(self):
        return len(self.spectra)
    
    def __getitem__(self, idx):
        spectrum = self.spectra[idx]
        target = self.targets[idx]
        
        if self.transform:
            spectrum = self.transform(spectrum)
            
        return spectrum, target

class EnhancedCNNModel(nn.Module):
    """增强版CNN模型，专为近红外光谱数据设计"""
    
    def __init__(self, input_size, output_size):
        """
        初始化增强版CNN模型
        Args:
            input_size: 输入特征维度
            output_size: 输出维度（成分数量）
        """
        super(EnhancedCNNModel, self).__init__()
        
        # 第一组卷积层 - 捕捉局部特征
        self.conv1 = nn.Conv1d(1, 32, kernel_size=11, stride=1, padding=5)
        self.bn1 = nn.BatchNorm1d(32)
        self.relu1 = nn.LeakyReLU(0.1)
        self.dropout1 = nn.Dropout(0.2)
        
        # 第二组卷积层 - 捕捉更高级特征
        self.conv2 = nn.Conv1d(32, 64, kernel_size=7, stride=1, padding=3)
        self.bn2 = nn.BatchNorm1d(64)
        self.relu2 = nn.LeakyReLU(0.1)
        self.dropout2 = nn.Dropout(0.2)
        
        # 第三组卷积层 - 进一步提取特征
        self.conv3 = nn.Conv1d(64, 128, kernel_size=5, stride=1, padding=2)
        self.bn3 = nn.BatchNorm1d(128)
        self.relu3 = nn.LeakyReLU(0.1)
        self.pool3 = nn.MaxPool1d(kernel_size=2)
        
        # 计算全连接层输入大小
        fc_input_size = 128 * (input_size // 2)
        
        # 全连接层进行预测
        self.fc1 = nn.Linear(fc_input_size, 256)
        self.bn4 = nn.BatchNorm1d(256)
        self.relu4 = nn.LeakyReLU(0.1)
        self.dropout4 = nn.Dropout(0.5)
        
        self.fc2 = nn.Linear(256, 128)
        self.bn5 = nn.BatchNorm1d(128)
        self.relu5 = nn.LeakyReLU(0.1)
        self.dropout5 = nn.Dropout(0.5)
        
        self.fc3 = nn.Linear(128, output_size)
        
    def forward(self, x):
        # 输入x形状: [batch_size, input_size]
        x = x.unsqueeze(1)  # 添加通道维度: [batch_size, 1, input_size]
        
        # 第一组卷积
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu1(x)
        x = self.dropout1(x)
        
        # 第二组卷积
        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu2(x)
        x = self.dropout2(x)
        
        # 第三组卷积
        x = self.conv3(x)
        x = self.bn3(x)
        x = self.relu3(x)
        x = self.pool3(x)
        
        # 展平
        x = x.view(x.size(0), -1)
        
        # 全连接层
        x = self.fc1(x)
        x = self.bn4(x)
        x = self.relu4(x)
        x = self.dropout4(x)
        
        x = self.fc2(x)
        x = self.bn5(x)
        x = self.relu5(x)
        x = self.dropout5(x)
        
        x = self.fc3(x)
        
        return x

def load_and_preprocess_data(file_path, apply_smoothing=True, apply_snv=True):
    """
    加载并预处理光谱数据，增加了更多预处理选项
    Args:
        file_path: Excel文件路径
        apply_smoothing: 是否应用Savitzky-Golay平滑
        apply_snv: 是否应用标准正态变量变换
    Returns:
        训练集和测试集的加载器，以及数据标准化器
    """
    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 读取数据
    try:
        excel_file = pd.ExcelFile(file_path)
        df = excel_file.parse('Sheet1')
    except Exception as e:
        raise Exception(f"读取Excel文件失败: {e}")
    
    # 打印数据基本信息
    print(f"数据基本信息：")
    df.info()
    
    # 提取光谱数据（假设光谱数据从第5列开始到最后一列）
    spectra_columns = df.columns[4:]
    spectra = df[spectra_columns].values
    
    # 提取目标成分数据
    try:
        targets = df[['Moisture', 'Oil', 'Protein', 'Starch']].values
    except KeyError as e:
        raise KeyError(f"找不到目标成分列: {e}")
    
    # 可视化原始光谱数据
    plot_spectra(spectra, spectra_columns, title="原始光谱数据")
    
    # 应用Savitzky-Golay平滑
    if apply_smoothing:
        spectra = savgol_filter(spectra, window_length=7, polyorder=3, deriv=0)
        plot_spectra(spectra, spectra_columns, title="Savitzky-Golay平滑后的光谱数据")
    
    # 应用标准正态变量变换(SNV)
    if apply_snv:
        spectra = snv_transform(spectra)
        plot_spectra(spectra, spectra_columns, title="SNV变换后的光谱数据")
    
    # 数据标准化
    scaler_spectra = StandardScaler()
    scaler_targets = StandardScaler()
    
    spectra_scaled = scaler_spectra.fit_transform(spectra)
    targets_scaled = scaler_targets.fit_transform(targets)
    
    # 可视化标准化后的光谱数据
    plot_spectra(spectra_scaled, spectra_columns, title="标准化后的光谱数据")
    
    # 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(
        spectra_scaled, targets_scaled, test_size=0.3, random_state=42, shuffle=True)
    
    print(f"训练集大小: {X_train.shape[0]}, 测试集大小: {X_test.shape[0]}")
    
    # 转换为PyTorch张量
    X_train_tensor = torch.FloatTensor(X_train)
    y_train_tensor = torch.FloatTensor(y_train)
    X_test_tensor = torch.FloatTensor(X_test)
    y_test_tensor = torch.FloatTensor(y_test)
    
    # 创建数据集
    train_dataset = NIRSpectroscopyDataset(X_train_tensor, y_train_tensor)
    test_dataset = NIRSpectroscopyDataset(X_test_tensor, y_test_tensor)
    
    # 创建数据加载器
    train_loader = DataLoader(train_dataset, batch_size=8, shuffle=True)
    test_loader = DataLoader(test_dataset, batch_size=8, shuffle=False)
    
    return train_loader, test_loader, scaler_spectra, scaler_targets, X_test, y_test, spectra_columns

def snv_transform(spectra):
    """
    标准正态变量变换(SNV)，用于消除颗粒大小、光散射等影响
    """
    mean = np.mean(spectra, axis=1).reshape(-1, 1)
    std = np.std(spectra, axis=1).reshape(-1, 1)
    return (spectra - mean) / std

def plot_spectra(spectra, wavelengths, title="光谱数据"):
    """
    可视化光谱数据
    """
    plt.figure(figsize=(12, 6))
    
    # 绘制前20个样本的光谱
    for i in range(min(20, spectra.shape[0])):
        plt.plot(wavelengths.astype(float), spectra[i, :], alpha=0.5)
    
    plt.title(title, fontsize=14)
    plt.xlabel("波长 (nm)", fontsize=12)
    plt.ylabel("吸光度", fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    # 确保标题包含有效字符，避免文件命名错误
    safe_title = "".join([c for c in title if c.isalnum() or c in [" ", "_", "-"]]).strip()
    plt.savefig(f"{safe_title}.png", dpi=300)
    plt.close()

def train_model(model, train_loader, criterion, optimizer, device, epochs=100, scheduler=None):
    """
    训练模型，增加了学习率调度和早停机制
    Args:
        model: 待训练的模型
        train_loader: 训练数据加载器
        criterion: 损失函数
        optimizer: 优化器
        device: 计算设备
        epochs: 训练轮数
        scheduler: 学习率调度器
    Returns:
        训练历史记录
    """
    model.train()
    train_history = {'loss': []}
    best_loss = float('inf')
    patience = 20  # 早停等待轮数
    counter = 0
    
    for epoch in range(epochs):
        running_loss = 0.0
        progress_bar = tqdm(enumerate(train_loader), total=len(train_loader))
        
        for i, (inputs, labels) in progress_bar:
            inputs, labels = inputs.to(device), labels.to(device)
            
            # 清零梯度
            optimizer.zero_grad()
            
            # 前向传播
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            
            # 反向传播和优化
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            progress_bar.set_description(f'Epoch {epoch+1}/{epochs}, Loss: {running_loss/(i+1):.6f}')
        
        # 记录每个epoch的损失
        epoch_loss = running_loss / len(train_loader)
        train_history['loss'].append(epoch_loss)
        
        # 更新学习率
        if scheduler:
            scheduler.step(epoch_loss)
        
        # 早停机制
        if epoch_loss < best_loss:
            best_loss = epoch_loss
            counter = 0
            # 保存最佳模型
            torch.save(model.state_dict(), 'best_model.pth')
        else:
            counter += 1
            if counter >= patience:
                print(f"早停触发: 在第 {epoch+1} 轮后停止训练")
                break
        
        print(f'Epoch {epoch+1}/{epochs}, Loss: {epoch_loss:.6f}, LR: {optimizer.param_groups[0]["lr"]:.8f}')
    
    # 加载最佳模型
    model.load_state_dict(torch.load('best_model.pth'))
    return train_history

def evaluate_model(model, test_loader, criterion, device, scaler_targets=None):
    """
    评估模型
    Args:
        model: 待评估的模型
        test_loader: 测试数据加载器
        criterion: 损失函数
        device: 计算设备
        scaler_targets: 目标变量的标准化器，用于逆变换
    Returns:
        预测值和真实值（原始尺度）
    """
    model.eval()
    all_preds = []
    all_labels = []
    test_loss = 0.0
    
    with torch.no_grad():
        for inputs, labels in test_loader:
            inputs, labels = inputs.to(device), labels.to(device)
            
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            
            test_loss += loss.item()
            all_preds.append(outputs.cpu().numpy())
            all_labels.append(labels.cpu().numpy())
    
    test_loss /= len(test_loader)
    print(f'Test Loss: {test_loss:.6f}')
    
    # 合并所有批次的预测和标签
    all_preds = np.vstack(all_preds)
    all_labels = np.vstack(all_labels)
    
    # 如果提供了标准化器，则将预测值和真实值转换回原始尺度
    if scaler_targets:
        all_preds = scaler_targets.inverse_transform(all_preds)
        all_labels = scaler_targets.inverse_transform(all_labels)
    
    return all_preds, all_labels

def visualize_results(predictions, targets, component_names):
    """
    可视化预测结果和评估指标
    Args:
        predictions: 预测值
        targets: 真实值
        component_names: 成分名称列表
    """
    # 创建一个大图
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    axes = axes.flatten()
    
    # 计算每个成分的评估指标
    for i, (ax, component) in enumerate(zip(axes, component_names)):
        # 计算评估指标
        mse = mean_squared_error(targets[:, i], predictions[:, i])
        r2 = r2_score(targets[:, i], predictions[:, i])
        
        # 绘制预测值与真实值的散点图
        sns.scatterplot(x=targets[:, i], y=predictions[:, i], alpha=0.7, ax=ax)
        
        # 绘制理想情况的对角线
        min_val = min(targets[:, i].min(), predictions[:, i].min())
        max_val = max(targets[:, i].max(), predictions[:, i].max())
        ax.plot([min_val, max_val], [min_val, max_val], 'r--', alpha=0.5)
        
        ax.set_title(f'{component}预测结果 (MSE: {mse:.4f}, R2: {r2:.4f})', fontsize=13)
        ax.set_xlabel('真实值', fontsize=12)
        ax.set_ylabel('预测值', fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.7)
    
    plt.suptitle('近红外光谱成分预测结果可视化', fontsize=16, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])  # 为suptitle留出空间
    plt.savefig('prediction_results.png', dpi=300)
    plt.show()
    
    # 绘制损失曲线
    plt.figure(figsize=(12, 7))
    plt.plot(train_history['loss'], label='训练损失', color='blue', linewidth=2.5)
    plt.title('模型训练损失曲线', fontsize=16)
    plt.xlabel('训练轮次 (Epoch)', fontsize=13)
    plt.ylabel('损失值 (MSE)', fontsize=13)
    plt.legend(fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('training_loss.png', dpi=300)
    plt.show()
    
    # 绘制预测误差分布
    plt.figure(figsize=(14, 10))
    for i, component in enumerate(component_names):
        error = predictions[:, i] - targets[:, i]
        plt.subplot(2, 2, i+1)
        sns.histplot(error, kde=True, bins=20, color='skyblue')
        plt.axvline(x=0, color='r', linestyle='--', alpha=0.7)
        plt.title(f'{component}预测误差分布', fontsize=14)
        plt.xlabel('预测误差', fontsize=12)
        plt.ylabel('频率', fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.5)
    
    plt.suptitle('各成分预测误差分布', fontsize=16, y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig('prediction_error_distribution.png', dpi=300)
    plt.show()

def save_predictions(predictions, targets, component_names, file_path='predictions.csv'):
    """
    保存预测结果到CSV文件
    Args:
        predictions: 预测值
        targets: 真实值
        component_names: 成分名称列表
        file_path: 保存文件路径
    """
    # 创建DataFrame
    data = {}
    for i, component in enumerate(component_names):
        data[f'{component}_真实值'] = targets[:, i]
        data[f'{component}_预测值'] = predictions[:, i]
        data[f'{component}_误差'] = predictions[:, i] - targets[:, i]
    
    df = pd.DataFrame(data)
    
    # 计算总体统计信息
    stats = {}
    for component in component_names:
        true = df[f'{component}_真实值']
        pred = df[f'{component}_预测值']
        stats[f'{component}_MSE'] = mean_squared_error(true, pred)
        stats[f'{component}_R2'] = r2_score(true, pred)
        stats[f'{component}_MAE'] = np.mean(np.abs(pred - true))
    
    # 添加统计信息到DataFrame
    stats_df = pd.DataFrame(stats, index=['统计信息'])
    
    # 保存到CSV
    with open(file_path, 'w', encoding='utf-8-sig') as f:  # 使用utf-8-sig编码确保中文正常保存
        df.to_csv(f, index=False)
        f.write('\n\n')
        stats_df.to_csv(f)
    
    print(f'预测结果已保存到 {file_path}')
    
    # 打印统计信息
    print("\n模型评估统计信息:")
    for component in component_names:
        print(f"{component}: MSE={stats[f'{component}_MSE']:.4f}, R²={stats[f'{component}_R²']:.4f}, MAE={stats[f'{component}_MAE']:.4f}")

def feature_importance_analysis(model, spectra_columns, device):
    """
    分析特征重要性
    """
    model.eval()
    
    # 创建一个随机样本用于分析
    random_sample = torch.randn(1, len(spectra_columns)).to(device)
    
    # 计算原始输出
    with torch.no_grad():
        original_output = model(random_sample)
    
    # 初始化特征重要性数组
    feature_importance = np.zeros(len(spectra_columns))
    
    # 逐个扰动特征，计算输出变化
    for i in range(len(spectra_columns)):
        # 创建扰动样本
        perturbed_sample = random_sample.clone()
        perturbed_sample[0, i] += 0.1  # 添加小扰动
        
        # 计算扰动后的输出
        with torch.no_grad():
            perturbed_output = model(perturbed_sample)
        
        # 计算特征重要性（输出变化的L2范数）
        importance = torch.norm(perturbed_output - original_output).item()
        feature_importance[i] = importance
    
    # 归一化重要性
    feature_importance = feature_importance / np.max(feature_importance)
    
    # 可视化特征重要性
    plt.figure(figsize=(16, 8))
    plt.plot(spectra_columns.astype(float), feature_importance, color='green', linewidth=2)
    plt.title('近红外光谱特征重要性分析', fontsize=16)
    plt.xlabel('波长 (nm)', fontsize=13)
    plt.ylabel('重要性', fontsize=13)
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig('feature_importance.png', dpi=300)
    plt.show()
    
    # 返回重要性最高的前10个波长
    top_indices = np.argsort(feature_importance)[-10:]
    top_wavelengths = spectra_columns[top_indices]
    top_importance = feature_importance[top_indices]
    
    print("\n最重要的10个波长:")
    for wl, imp in zip(top_wavelengths, top_importance):
        print(f"波长: {wl} nm, 重要性: {imp:.4f}")
    
    return feature_importance, top_wavelengths

def main():
    # 设置设备
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'使用设备: {device}')
    
    try:
        # 直接使用指定路径的Excel文件
        file_path = r'C:\Users\xh990320\Desktop\作业\玉米的近红外光谱数据.xlsx'
        
        # 创建保存结果的目录
        results_dir = '近红外光谱分析结果'
        if not os.path.exists(results_dir):
            os.makedirs(results_dir)
        os.chdir(results_dir)
        
        # 加载和预处理数据
        print("\n开始加载和预处理数据...")
        train_loader, test_loader, scaler_spectra, scaler_targets, X_test, y_test, spectra_columns = load_and_preprocess_data(file_path)
        
        # 初始化模型
        print("\n初始化模型...")
        input_size = X_test.shape[1]  # 光谱数据维度
        output_size = y_test.shape[1]  # 成分数量
        model = EnhancedCNNModel(input_size, output_size).to(device)
        
        # 定义损失函数和优化器
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.0005, weight_decay=1e-5)
        
        # 学习率调度器
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=10, verbose=True)
        
        # 训练模型
        print('\n开始训练模型...')
        global train_history  # 为了在visualize_results中使用
        train_history = train_model(model, train_loader, criterion, optimizer, device, epochs=200, scheduler=scheduler)
        
        # 评估模型
        print('\n开始评估模型...')
        predictions, targets = evaluate_model(model, test_loader, criterion, device, scaler_targets)
        
        # 特征重要性分析
        print('\n进行特征重要性分析...')
        feature_importance, top_wavelengths = feature_importance_analysis(model, spectra_columns, device)
        
        # 可视化结果
        print('\n可视化分析结果...')
        component_names = ['水分', '油脂', '蛋白质', '淀粉']
        visualize_results(predictions, targets, component_names)
        
        # 保存预测结果
        save_predictions(predictions, targets, component_names)
        
        # 保存模型
        torch.save(model.state_dict(), 'nir_spectroscopy_model.pth')
        print('\n模型已保存为 nir_spectroscopy_model.pth')
        
        print("\n分析完成！所有结果已保存到 '近红外光谱分析结果' 文件夹中。")
        
    except Exception as e:
        print(f"\n程序执行出错: {e}")
        exit(1)

if __name__ == '__main__':
    main()
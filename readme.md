
# SearchGram

将电报消息缓存到本地，解决中文、日文、韩文搜索困难的问题。其使用Meilisearch为数据库，Redis缓存，由python构建而成，由[原项目](https://github.com/tgbot-collection/SearchGram)修改而来，可以在性能较弱的机器上运行。
问题来源已久

* https://github.com/tdlib/td/issues/1004
* https://bugs.telegram.org/c/724


## 功能特点

- 跨所有同步聊天的全局消息搜索
- 特定类型搜索（如群组、频道、私聊）
- 特定用户搜索
- 精确匹配和模糊搜索选项
- 消息删除（所有消息、特定聊天、特定用户）
- 客户端管理（启动、停止、重启）
- 同步管理（添加、移除、列出同步的聊天）
- 搜索结果分页
- 敏感操作仅限管理员访问

## 前置要求

- 申请[Telegram API](https://my.telegram.org)
	实测需家宽IP
- 从@BotFather申请telegram机器人
- Python 3.7+
- Redis
- MeiliSearch

## 安装

1. 克隆仓库：
```
   git clone https://github.com/clionertr/SearchGram.git
   cd SearchGram
```

2. 创建并激活虚拟环境：
   ```
   python -m venv venv
   source venv/bin/activate  # Windows 上使用 `venv\Scripts\activate`
   ```

3. 安装所需包：
   ```
   pip install -r requirements.txt
   ```

4. 设置您的配置：
   - 将 `config.py.example` 重命名为 `config.py`
   - 填写的 Telegram API 凭证和其他必要信息
   - 设置sysnc.ini为可读写
5. 初始化数据库和搜索引擎：
   ```
   python client.py
   ```
   按照提示进行
   获取session后使用`CTRL+C`退出脚本


## 使用方法
0.Linux可使用`screen`挂起

1.激活虚拟环境：
   ```
   python -m venv venv
   source venv/bin/activate  # Windows 上使用 `venv\Scripts\activate`
   ```

2. 启动机器人：
   ```
   python bot.py
   ```

3. 启动客户端进行消息同步（可选，可用bot命令启动client.py）：
   ```
   python client.py
   ```

4. 在 Telegram 中，与您的机器人开始对话，并使用 `/help` 命令查看可用选项。

## 命令

- `/start`：启动机器人
- `/help`：显示帮助信息
- `/ping`：检查机器人和数据库状态
- `/delete`：删除消息（可选择全部、特定聊天或特定用户）
- `/start_client`、`/stop_client`、`/restart_client`：管理客户端脚本
- `/add_sync`、`/remove_sync`、`/list_sync`：管理同步的聊天（未完全测试，可能有bug）
- `/view_client_log`: 查看client.py的日志


## 配置

sync.ini配置同步
接受ID与用户名或群组名

[sync] :   下载包含群组/用户的所有历史消息	
白名单 ：只同步白名单内群组/用户消息，无历史消息
黑名单 ：不同步其中白名单内群组/用户消息

## 性能
在我的1CPU 1G内存的VPS上，同步30w历史消息期间花费约30小时，瓶颈为IO的写操作。74w消息的数据大小为2.5GiB。一般状态下仅需考虑内存大小。

## 省流
假装这里有个一键脚本

## 致谢
感谢开源
感谢Claude3.5
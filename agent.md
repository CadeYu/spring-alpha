# Spring Alpha Development Guidelines

> AI Agent 与开发者协作规范

## 1. 项目结构

```
spring-alpha/
├── backend/                 # Spring Boot 后端 (Java 21)
│   ├── src/main/java/       # Java 源码
│   ├── src/main/resources/  # 配置文件
│   ├── pom.xml              # Maven 配置
│   └── .env                 # 本地环境变量 (gitignored)
├── frontend/                # Next.js 前端
│   ├── src/                 # 源码
│   └── package.json         # 依赖配置
├── .gitignore               # Git 忽略规则
├── start_backend.sh         # 启动脚本 (gitignored, 包含 API Key)
└── start_backend.example.sh # 启动脚本模板
```

## 2. 敏感信息管理 (CRITICAL)

### 绝对禁止提交的内容

| 类型 | 示例 | 处理方式 |
|------|------|----------|
| API Keys | `gsk_xxx`, `sk-xxx` | 使用环境变量 `${VAR_NAME}` |
| 密码 | 数据库密码、服务密码 | 存放在 `.env` 文件 |
| 私钥 | `*.pem`, `*.key` | 加入 `.gitignore` |
| 本地配置 | `application-local.yml` | 加入 `.gitignore` |

### 正确做法

```yaml
# application.yml - 使用环境变量占位符
spring:
  ai:
    openai:
      api-key: ${GROQ_API_KEY:}  # 从环境变量读取，默认为空
```

```bash
# .env 或 start_backend.sh (gitignored)
export GROQ_API_KEY=your_actual_key_here
```

### 提交前检查清单

- [ ] `git diff --cached` 检查暂存内容
- [ ] 确认无硬编码的 API Key / 密码
- [ ] 确认 `.env` 文件未被跟踪
- [ ] 确认 `target/` 目录未被跟踪

## 3. Git 版本控制规范

### 3.1 分支策略

```
master (main)     # 生产分支，保持稳定
  └── feature/*   # 功能分支
  └── fix/*       # 修复分支
  └── refactor/*  # 重构分支
```

### 3.2 Commit Message 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <description>

[optional body]
```

**Type 类型：**

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(api): add SEC filing endpoint` |
| `fix` | Bug 修复 | `fix(crawler): handle 404 response` |
| `refactor` | 重构 | `refactor(service): extract AI strategy` |
| `docs` | 文档 | `docs: update README` |
| `chore` | 杂项 | `chore: update gitignore` |
| `test` | 测试 | `test: add unit tests for SecService` |

**Scope 范围：**
- `backend` / `frontend` / `fullstack`
- `api` / `ui` / `config`
- 具体模块名

### 3.3 提交流程

```bash
# 1. 查看当前状态
git status

# 2. 查看具体变更（检查是否有敏感信息）
git diff

# 3. 暂存文件
git add <files>

# 4. 再次确认暂存内容
git diff --cached

# 5. 提交
git commit -m "feat(scope): description"

# 6. 推送
git push origin master
```

### 3.4 敏感信息泄露应急处理

如果不小心提交了敏感信息：

```bash
# 情况 1: 还没 push - 直接 reset
git reset --soft HEAD~1   # 撤销 commit，保留修改
# 或
git reset --hard HEAD~1   # 撤销 commit，丢弃修改

# 情况 2: 已经 push - 需要重写历史
git reset --hard <clean_commit_hash>
git push --force origin master  # 危险操作，确保无他人协作

# 情况 3: 已被他人拉取 - 必须轮换密钥
# 去对应平台 regenerate API Key
```

## 4. 开发环境设置

### 4.1 后端启动

```bash
# 方法 1: 使用启动脚本
cp start_backend.example.sh start_backend.sh
# 编辑 start_backend.sh 填入你的 API Key
chmod +x start_backend.sh
./start_backend.sh

# 方法 2: 直接设置环境变量
export GROQ_API_KEY=your_key_here
cd backend && ./mvnw spring-boot:run
```

### 4.2 前端启动

```bash
cd frontend
npm install
npm run dev
```

### 4.3 访问地址

- Frontend: http://localhost:3000
- Backend API: http://localhost:8081
- Health Check: http://localhost:8081/api/health

## 5. AI Agent 协作规范

### 5.1 Agent 可以做的

- [x] 读取和修改源代码
- [x] 运行构建和测试命令
- [x] 创建新文件和目录
- [x] 执行 git 操作（add, commit, status, diff）
- [x] 分析错误并提供修复方案

### 5.2 Agent 需要确认的

- [ ] `git push` - 推送到远程
- [ ] `git reset --hard` - 丢弃本地修改
- [ ] `git push --force` - 强制推送
- [ ] 删除文件或目录
- [ ] 修改 `.env` 或包含密钥的文件

### 5.3 Agent 绝不能做的

- 在代码中硬编码 API Key 或密码
- 提交 `.env` 文件
- 在日志或输出中打印完整的 API Key
- 将敏感信息发送到外部服务

## 6. 代码质量标准

### 6.1 后端 (Java)

- 使用 Spring Boot 3.x 最佳实践
- Service 层使用接口 + 实现类
- 异常统一处理
- 使用 SLF4J 日志

### 6.2 前端 (TypeScript)

- 使用 TypeScript 严格模式
- 组件使用函数式组件 + Hooks
- 使用 Shadcn/ui 组件库
- API 调用错误处理

## 7. 常用命令速查

```bash
# Git
git status                    # 查看状态
git log --oneline -10         # 查看最近 10 条提交
git diff                      # 查看未暂存的修改
git diff --cached             # 查看已暂存的修改
git reset --soft HEAD~1       # 撤销最后一次提交（保留修改）

# Backend
cd backend && ./mvnw spring-boot:run          # 启动
cd backend && ./mvnw clean package            # 打包
cd backend && ./mvnw test                     # 测试

# Frontend
cd frontend && npm run dev                    # 开发模式
cd frontend && npm run build                  # 生产构建
cd frontend && npm run lint                   # 代码检查
```

---

*Last updated: 2026-01-22*

<template>
  <div class="home-container">
    <div class="hero-section">
      <div class="hero-content">
        <h1 class="hero-title">学在华邮件助手</h1>
        <p class="hero-subtitle">简单易用的通用邮件收件工具</p>
        <div class="hero-buttons">
          <el-button type="primary" size="large" @click="navigateToEmails" class="primary-btn hover-scale">开始使用</el-button>
          <el-button size="large" class="secondary-btn hover-scale" @click="scrollToFeatures">了解更多</el-button>
        </div>
      </div>
      <div class="hero-decoration">
        <div class="hero-shape shape-1"></div>
        <div class="hero-shape shape-2"></div>
        <div class="hero-shape shape-3"></div>
      </div>
    </div>

    <div class="features-section" ref="featuresSection">
      <h2 class="section-title">功能特点</h2>
      <div class="features-grid">
        <div class="feature-card" v-for="(feature, index) in features" :key="index">
          <div class="feature-icon-wrapper" :class="`bg-${feature.color}`">
            <el-icon size="30"><component :is="feature.icon" /></el-icon>
          </div>
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.description }}</p>
        </div>
      </div>
    </div>

    <div class="stats-section">
      <h2 class="section-title">效率至上</h2>
      <div class="stats-grid">
        <div class="stat-card" v-for="(stat, index) in stats" :key="index">
          <div class="stat-number">{{ stat.value }}</div>
          <div class="stat-desc">{{ stat.description }}</div>
        </div>
      </div>
    </div>

    <div class="quick-start-section">
      <h2 class="section-title">快速开始</h2>
      <div class="steps-container">
        <div class="step-item" v-for="(step, index) in steps" :key="index">
          <div class="step-number">{{ index + 1 }}</div>
          <div class="step-content">
            <h3>{{ step.title }}</h3>
            <p>{{ step.description }}</p>
          </div>
        </div>
      </div>
    </div>

    <div class="cta-section">
      <div class="cta-content">
        <h2>开始使用学在华邮件助手</h2>
        <p>简单几步，高效管理您的所有邮箱</p>
        <el-button type="primary" size="large" @click="navigateToEmails" class="cta-button hover-scale">立即开始</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Briefcase, Management, Connection, Cpu, Search, Document, AlarmClock, Setting } from '@element-plus/icons-vue'

const router = useRouter()
const featuresSection = ref(null)

const features = [
  {
    icon: 'Briefcase',
    title: '邮箱管理',
    description: '集中管理多个邮箱账户，支持添加、删除和维护各类邮箱',
    color: 'primary'
  },
  {
    icon: 'Management',
    title: '邮箱批量管理',
    description: '支持多选、全选邮箱，进行批量删除、收信，允许单个邮箱手动收信',
    color: 'success'
  },
  {
    icon: 'Connection',
    title: '实时通信',
    description: 'WebSocket实时通信，及时获取操作进度和结果反馈',
    color: 'warning'
  },
  {
    icon: 'Cpu',
    title: '多线程支持',
    description: '收件操作采用多线程处理，提高效率，支持多邮箱并行处理',
    color: 'danger'
  },
  {
    icon: 'Search',
    title: '强大的搜索',
    description: '快速搜索和过滤邮件内容，轻松找到需要的信息',
    color: 'info'
  },
  {
    icon: 'Document',
    title: '数据分析',
    description: '邮件数据统计与分析，帮助您更好地了解邮件趋势',
    color: 'primary'
  }
]

const stats = [
  { value: '100+', description: '邮箱并行处理' },
  { value: '10x', description: '收件速度提升' },
  { value: '24/7', description: '全天候监控' }
]

const steps = [
  {
    title: '添加邮箱',
    description: '在"邮箱管理"页面点击"添加邮箱"，单个或批量添加您的邮箱账户'
  },
  {
    title: '管理邮箱',
    description: '在"邮箱管理"页面查看所有导入的邮箱，可以进行单个或批量操作'
  },
  {
    title: '收取邮件',
    description: '点击"收信"按钮开始收取邮件，可以查看实时进度'
  },
  {
    title: '查看邮件',
    description: '点击邮箱查看已收取的所有邮件内容'
  }
]

const navigateToEmails = () => {
  router.push('/emails')
}

const scrollToFeatures = () => {
  featuresSection.value.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
.home-container {
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px;
}

.hero-section {
  background: linear-gradient(135deg, var(--primary-color) 0%, #60a5fa 100%);
  color: white;
  border-radius: var(--border-radius-lg);
  padding: 80px 30px;
  margin-bottom: 60px;
  text-align: center;
  box-shadow: var(--box-shadow-lg);
  position: relative;
  overflow: hidden;
}

.hero-decoration {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
  pointer-events: none;
}

.hero-shape {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
}

.shape-1 {
  width: 300px;
  height: 300px;
  top: -100px;
  right: -100px;
  animation: float 15s infinite ease-in-out;
}

.shape-2 {
  width: 200px;
  height: 200px;
  bottom: -50px;
  left: -50px;
  animation: float 20s infinite ease-in-out reverse;
}

.shape-3 {
  width: 150px;
  height: 150px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  animation: pulse 10s infinite ease-in-out;
}

@keyframes float {
  0% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-20px) rotate(5deg); }
  100% { transform: translateY(0) rotate(0deg); }
}

@keyframes pulse {
  0% { transform: translate(-50%, -50%) scale(1); opacity: 0.7; }
  50% { transform: translate(-50%, -50%) scale(1.2); opacity: 0.3; }
  100% { transform: translate(-50%, -50%) scale(1); opacity: 0.7; }
}

.hero-title {
  font-size: 3.5rem;
  margin-bottom: 16px;
  font-weight: 800;
  position: relative;
  display: inline-block;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
  animation: fadeIn 1s ease-out;
}

.hero-subtitle {
  font-size: 1.5rem;
  margin-bottom: 40px;
  opacity: 0.9;
  animation: fadeIn 1s ease-out 0.3s forwards;
  opacity: 0;
}

.hero-buttons {
  display: flex;
  gap: 20px;
  justify-content: center;
  animation: fadeIn 1s ease-out 0.5s forwards;
  opacity: 0;
}

.primary-btn {
  background: white;
  color: var(--primary-color);
  border: none;
  box-shadow: var(--box-shadow);
  padding: 12px 30px;
}

.secondary-btn {
  background: rgba(255, 255, 255, 0.2);
  color: white;
  border: 2px solid white;
  padding: 12px 30px;
}

.section-title {
  text-align: center;
  font-size: 2.2rem;
  margin-bottom: 50px;
  color: var(--primary-text-color);
  position: relative;
  display: inline-block;
  left: 50%;
  transform: translateX(-50%);
}

.section-title::after {
  content: '';
  position: absolute;
  bottom: -15px;
  left: 50%;
  transform: translateX(-50%);
  width: 60px;
  height: 4px;
  background-color: var(--primary-color);
  border-radius: var(--border-radius-full);
}

.features-section {
  margin-bottom: 80px;
  scroll-margin-top: 100px;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 30px;
}

.feature-card {
  background-color: white;
  padding: 30px;
  border-radius: var(--border-radius-md);
  box-shadow: var(--box-shadow);
  text-align: center;
  transition: all var(--transition-normal);
  border-top: 5px solid transparent;
}

.feature-card:hover {
  transform: translateY(-10px);
  box-shadow: var(--box-shadow-lg);
}

.feature-icon-wrapper {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 20px;
  color: white;
}

.bg-primary { background-color: var(--primary-color); }
.bg-success { background-color: var(--success-color); }
.bg-warning { background-color: var(--warning-color); }
.bg-danger { background-color: var(--danger-color); }
.bg-info { background-color: var(--info-color); }

.feature-card h3 {
  margin: 20px 0 15px;
  color: var(--primary-text-color);
  font-size: 1.4rem;
}

.feature-card p {
  color: var(--regular-text-color);
  line-height: 1.6;
}

.stats-section {
  margin-bottom: 80px;
  background-color: var(--background-color-light);
  padding: 60px 40px;
  border-radius: var(--border-radius-lg);
  box-shadow: var(--box-shadow);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 30px;
}

.stat-card {
  text-align: center;
  padding: 30px;
  transition: transform var(--transition-normal);
  position: relative;
}

.stat-card::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 40px;
  height: 3px;
  background-color: var(--primary-color);
  border-radius: var(--border-radius-full);
  transition: width var(--transition-normal);
}

.stat-card:hover::after {
  width: 70%;
}

.stat-card:hover {
  transform: translateY(-5px);
}

.stat-number {
  font-size: 3.5rem;
  font-weight: 800;
  color: var(--primary-color);
  margin-bottom: 15px;
}

.stat-desc {
  font-size: 1.2rem;
  color: var(--regular-text-color);
  font-weight: 500;
}

.quick-start-section {
  margin-bottom: 80px;
}

.steps-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.step-item {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  background-color: white;
  padding: 25px;
  border-radius: var(--border-radius-md);
  box-shadow: var(--box-shadow);
  transition: transform var(--transition-normal), box-shadow var(--transition-normal);
  border-left: 5px solid var(--primary-color);
}

.step-item:hover {
  transform: translateX(10px);
  box-shadow: var(--box-shadow-md);
}

.step-number {
  background-color: var(--primary-color);
  color: white;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: bold;
  font-size: 1.2rem;
  flex-shrink: 0;
}

.step-content h3 {
  margin-top: 0;
  margin-bottom: 10px;
  color: var(--primary-text-color);
  font-size: 1.2rem;
}

.step-content p {
  margin: 0;
  color: var(--regular-text-color);
  line-height: 1.6;
}

.cta-section {
  background: linear-gradient(135deg, #38bdf8 0%, var(--primary-color) 100%);
  color: white;
  border-radius: var(--border-radius-lg);
  padding: 60px 30px;
  margin-bottom: 40px;
  text-align: center;
  box-shadow: var(--box-shadow-lg);
}

.cta-content h2 {
  font-size: 2.2rem;
  margin-bottom: 16px;
  font-weight: 700;
}

.cta-content p {
  font-size: 1.2rem;
  margin-bottom: 30px;
  opacity: 0.9;
}

.cta-button {
  background: white;
  color: var(--primary-color);
  border: none;
  box-shadow: var(--box-shadow);
  padding: 12px 30px;
  font-size: 1.1rem;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 768px) {
  .hero-title {
    font-size: 2.5rem;
  }

  .hero-subtitle {
    font-size: 1.2rem;
    margin-bottom: 30px;
  }

  .hero-buttons {
    flex-direction: column;
    gap: 15px;
    align-items: center;
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .step-item {
    padding: 20px;
  }

  .cta-content h2 {
    font-size: 1.8rem;
  }
}

@media (max-width: 480px) {
  .hero-section {
    padding: 50px 20px;
  }

  .hero-title {
    font-size: 2rem;
  }

  .section-title {
    font-size: 1.8rem;
  }

  .feature-card {
    padding: 20px;
  }

  .stat-number {
    font-size: 2.5rem;
  }
}
</style>

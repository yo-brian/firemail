import { createRouter, createWebHistory } from 'vue-router'
import store from '@/store'
import logger from '@/utils/debugLogger'
import MailListView from '@/views/MailListView.vue'
import SentMailListView from '@/views/SentMailListView.vue'
import EmailsView from '@/views/EmailsView.vue'
import SearchView from '@/views/SearchView.vue'
import AboutView from '@/views/AboutView.vue'
import UsersView from '@/views/admin/UsersView.vue'
import EmailDetailView from '@/views/EmailDetailView.vue'
import ImportView from '@/views/ImportView.vue'
import LoginView from '@/views/auth/LoginView.vue'
import RegisterView from '@/views/auth/RegisterView.vue'
import AccountView from '@/views/auth/AccountView.vue'
import SimplifiedUsersView from '@/views/admin/SimplifiedUsersView.vue'
import ForbiddenView from '@/views/ForbiddenView.vue'
import NotFoundView from '@/views/NotFoundView.vue'

// 路由守卫 - 检查认证状态
const requireAuth = (to, from, next) => {
  const isAuthenticated = store.getters['auth/isAuthenticated']
  
  if (!isAuthenticated) {
    // 保存原始目标路由，以便登录后重定向
    next({ 
      name: 'login', 
      query: { redirect: to.fullPath }
    })
  } else {
    next()
  }
}

// 路由守卫 - 检查管理员权限
const requireAdmin = (to, from, next) => {
  const isAuthenticated = store.getters['auth/isAuthenticated']
  const isAdmin = store.getters['auth/isAdmin']
  
  if (!isAuthenticated) {
    next({ 
      name: 'login', 
      query: { redirect: to.fullPath }
    })
  } else if (!isAdmin) {
    next({ name: 'forbidden' })
  } else {
    next()
  }
}

// 路由守卫 - 已登录用户不可访问
const guestOnly = (to, from, next) => {
  const isAuthenticated = store.getters['auth/isAuthenticated']
  
  if (isAuthenticated) {
    next({ name: 'home' })
  } else {
    next()
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: MailListView,
      meta: { requiresAuth: true }
    },
    {
      path: '/emails',
      name: 'emails',
      component: EmailsView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth
    },
    {
      path: '/emails/:id',
      name: 'email-detail',
      component: EmailDetailView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth,
      props: route => ({ id: Number(route.params.id) })
    },
    {
      path: '/import',
      name: 'import',
      component: ImportView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth
    },
    {
      path: '/mail-list',
      name: 'mail-list',
      component: MailListView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth
    },
    {
      path: '/sent',
      name: 'sent-mails',
      component: SentMailListView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth
    },
    {
      path: '/search',
      name: 'search',
      component: SearchView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth
    },
    {
      path: '/about',
      name: 'about',
      component: AboutView
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { guestOnly: true },
      beforeEnter: guestOnly
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { guestOnly: true },
      beforeEnter: guestOnly
    },
    {
      path: '/account',
      name: 'account',
      component: AccountView,
      meta: { requiresAuth: true },
      beforeEnter: requireAuth
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: UsersView,
      meta: { requiresAdmin: true },
      beforeEnter: requireAdmin
    },
    {
      path: '/admin/users-simple',
      name: 'admin-users-simple',
      component: SimplifiedUsersView,
      meta: { requiresAdmin: true },
      beforeEnter: requireAdmin
    },
    {
      path: '/forbidden',
      name: 'forbidden',
      component: ForbiddenView
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundView
    }
  ]
})

// 全局前置守卫
router.beforeEach((to, from, next) => {
  logger.debug('router', 'beforeEach', {
    from: from.fullPath,
    to: to.fullPath,
    name: to.name
  })
  // 检查目标路由是否需要认证
  if (to.matched.some(record => record.meta.requiresAuth)) {
    const isAuthenticated = store.getters['auth/isAuthenticated']
    
    if (!isAuthenticated) {
      next({
        name: 'login',
        query: { redirect: to.fullPath }
      })
    } else {
      next()
    }
  } 
  // 检查目标路由是否需要管理员权限
  else if (to.matched.some(record => record.meta.requiresAdmin)) {
    const isAuthenticated = store.getters['auth/isAuthenticated']
    const isAdmin = store.getters['auth/isAdmin']
    
    if (!isAuthenticated) {
      next({
        name: 'login',
        query: { redirect: to.fullPath }
      })
    } else if (!isAdmin) {
      next({ name: 'forbidden' })
    } else {
      next()
    }
  } 
  // 对于仅限游客访问的路由
  else if (to.matched.some(record => record.meta.guestOnly)) {
    const isAuthenticated = store.getters['auth/isAuthenticated']
    
    if (isAuthenticated) {
      next({ name: 'home' })
    } else {
      next()
    }
  } 
  // 其他路由
  else {
    next()
  }
})

router.afterEach((to, from) => {
  logger.debug('router', 'afterEach', {
    from: from.fullPath,
    to: to.fullPath,
    name: to.name
  })
})

router.onError((error, to) => {
  logger.error('router', 'onError', {
    to: to?.fullPath,
    name: to?.name,
    message: error?.message
  })
})

export default router 

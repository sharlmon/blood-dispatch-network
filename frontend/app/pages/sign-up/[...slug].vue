<script setup lang="ts">
import { clerkAppearance } from '~/utils/clerkTheme'

definePageMeta({ layout: 'auth' })
const { public: { authEnabled, demoAuth } } = useRuntimeConfig()
useHead({ title: 'Create account · Blood Dispatch' })
</script>

<template>
  <AuthSplash :title="'Join your\nhospital\'s network'" sub="Create your account, then set up your hospital." cta="Create account">
    <SignUp v-if="authEnabled" :appearance="clerkAppearance" sign-in-url="/sign-in" />
    <DemoAuthForm v-else-if="demoAuth" mode="up" />
    <DemoNotice v-else />
  </AuthSplash>
</template>

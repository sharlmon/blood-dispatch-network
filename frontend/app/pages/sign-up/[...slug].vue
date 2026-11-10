<script setup lang="ts">
import { clerkAppearance } from '~/utils/clerkTheme'

definePageMeta({ layout: 'auth' })
const { public: { authEnabled } } = useRuntimeConfig()
useHead({ title: 'Create account · Blood Dispatch' })
</script>

<template>
  <AuthSplash :title="'Join your\nhospital\'s network'" sub="Create your account, then set up your hospital.">
    <SignUp v-if="authEnabled" :appearance="clerkAppearance" sign-in-url="/sign-in" />
    <DemoNotice v-else />
  </AuthSplash>
</template>

<script setup lang="ts">
import { clerkAppearance } from '~/utils/clerkTheme'

definePageMeta({ layout: 'auth' })
const { public: { authEnabled } } = useRuntimeConfig()
useHead({ title: 'Sign in · Blood Dispatch' })
</script>

<template>
  <AuthSplash title="Every hospital could be a lifeline" sub="Saving lives, one spare bag at a time.">
    <SignIn v-if="authEnabled" :appearance="clerkAppearance" sign-up-url="/sign-up" />
    <DemoNotice v-else />
  </AuthSplash>
</template>

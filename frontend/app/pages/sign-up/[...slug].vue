<script setup lang="ts">
import { clerkAppearance } from '~/utils/clerkTheme'

definePageMeta({ layout: 'auth' })
useHead({ title: 'Create account · Blood Dispatch' })
</script>

<template>
  <AuthSplash title="Join your hospital's network" sub="Create your account, then set up your hospital.">
    <SignUp :appearance="clerkAppearance" sign-in-url="/sign-in" />
  </AuthSplash>
</template>

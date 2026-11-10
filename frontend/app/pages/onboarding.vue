<script setup lang="ts">
import { clerkAppearance } from '~/utils/clerkTheme'

definePageMeta({ layout: 'auth' })
useHead({ title: 'Set up your hospital · Blood Dispatch' })

const { public: { authEnabled } } = useRuntimeConfig()
if (authEnabled) {
  const { orgId } = useAuth()
  watchEffect(() => { if (orgId.value) navigateTo('/request') })
}
</script>

<template>
  <AuthSplash :title="'Set up your\nhospital'" sub="Join your hospital or create it. Requests are sent on its behalf.">
    <OrganizationList v-if="authEnabled" :appearance="clerkAppearance" :hide-personal="true" after-select-organization-url="/request" after-create-organization-url="/request" />
    <DemoNotice v-else />
  </AuthSplash>
</template>

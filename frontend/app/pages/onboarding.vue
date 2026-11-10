<script setup lang="ts">
import { clerkAppearance } from '~/utils/clerkTheme'

definePageMeta({ layout: 'auth' })
useHead({ title: 'Set up your hospital · Blood Dispatch' })

const { orgId } = useAuth()
watchEffect(() => { if (orgId.value) navigateTo('/request') })
</script>

<template>
  <AuthSplash title="Set up your hospital" sub="Join your hospital or create it. Requests are sent on its behalf.">
    <OrganizationList :appearance="clerkAppearance" :hide-personal="true" after-select-organization-url="/request" after-create-organization-url="/request" />
  </AuthSplash>
</template>

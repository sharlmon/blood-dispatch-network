/** Who is signed in and which hospital they act for (demo values when login is off). */
export function useSite() {
  const { public: { authEnabled, demoAuth } } = useRuntimeConfig()
  if (authEnabled) {
    const { user } = useUser()
    const { organization } = useOrganization()
    return {
      firstName: computed(() => user.value?.firstName ?? ''),
      hospital: computed(() => organization.value?.name ?? 'Your hospital')
    }
  }
  if (demoAuth) {
    const { account } = useDemoAccount()
    return {
      firstName: computed(() => account.value?.name.split(' ')[0] ?? ''),
      hospital: computed(() => account.value?.hospital ?? 'Your hospital')
    }
  }
  return { firstName: computed(() => ''), hospital: computed(() => 'Hillside Hospital') }
}

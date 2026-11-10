/** Who is signed in and which hospital they act for (demo values when login is off). */
export function useSite() {
  const { public: { authEnabled } } = useRuntimeConfig()
  if (authEnabled) {
    const { user } = useUser()
    const { organization } = useOrganization()
    return {
      firstName: computed(() => user.value?.firstName ?? ''),
      hospital: computed(() => organization.value?.name ?? 'Your hospital')
    }
  }
  return { firstName: computed(() => ''), hospital: computed(() => 'Hillside Hospital') }
}

const c = (cx: number, cy: number, r: number) =>
  `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`

export const DROP = 'M12 3c3.6 4.3 6 7.5 6 10.5a6 6 0 0 1-12 0C6 10.5 8.4 7.3 12 3z'

/** 24px grid, 1.75 stroke, round caps. One path per icon. */
export const ICONS: Record<string, string> = {
  hospital: 'M4 21V8l8-4 8 4v13M9 21v-5h6v5M12 9v4M10 11h4',
  centre: 'M4 21V10l8-6 8 6v11M12 11c1.8 2.1 3 3.5 3 5a3 3 0 0 1-6 0c0-1.5 1.2-2.9 3-5z',
  drop: DROP,
  units: 'M12 3 3 8l9 5 9-5-9-5zM3 13l9 5 9-5',
  window: 'M3 12h18M3 8v8M21 8v8' + c(12, 12, 2.5),
  clock: c(12, 12, 9) + 'M12 7v5l3 2',
  route: c(6, 19, 2) + c(18, 5, 2) + 'M8 19h6a3.5 3.5 0 0 0 0-7h-4a3.5 3.5 0 0 1 0-7h6',
  confirmed: 'M12 3l8 3v6c0 4.5-3.3 8-8 9-4.7-1-8-4.5-8-9V6l8-3zM8.5 12l2.5 2.5 4.5-5',
  sms: 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5',
  call: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z',
  warning: 'M12 3 2 20h20L12 3zM12 10v4M12 17h.01',
  transfer: 'M3 16V7h11v9M14 10h4l3 3v3h-7' + c(7, 17, 2) + c(17, 17, 2) + 'M7 9.5v3M5.5 11h3',
  edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1z',
  bell: 'M6 16v-5a6 6 0 0 1 12 0v5l2 2H4l2-2zM10 21h4',
  audit: 'M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5',
  results: 'M4 20V10M10 20V4M16 20v-7M22 20H2',
  home: 'M4 11l8-7 8 7v9H4zM10 20v-6h4v6',
  pin: 'M12 21s-7-6-7-11a7 7 0 0 1 14 0c0 5-7 11-7 11zM12 8a2 2 0 1 0 0 4a2 2 0 1 0 0-4',
  back: 'M15 5l-7 7 7 7',
  search: c(11, 11, 8) + 'M21 21l-4.3-4.3',
  check: 'M5 12l5 5 9-10',
  close: 'M6 6l12 12M18 6L6 18',
  copy: 'M9 9h10v10H9zM5 15V5h10',
  list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  groupO: c(12, 12, 9) + 'M10 9.5a2.5 2.5 0 0 1 5 0v5a2.5 2.5 0 0 1-5 0z'
}

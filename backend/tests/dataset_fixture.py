"""Small generated synthetic dataset, never represented as the starter dataset."""
import csv

from engine.load import REQUEST_COLUMNS


def write_dataset(root):
    root.mkdir(parents=True, exist_ok=True)
    def table(name, columns, rows):
        with (root / (name + '.csv')).open('w', newline='') as output:
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(rows)
    table('facilities', ['facility_id', 'name', 'facility_type', 'supply_centre_id', 'has_blood_fridge_backup_power', 'connectivity'], [
        ('HSP-R', 'Synthetic requester', 'county_hospital', 'RBTC-A', True, '4G'),
        ('RBTC-A', 'Synthetic centre A', 'regional_blood_centre', '', True, '4G'),
        ('RBTC-B', 'Synthetic centre B', 'regional_blood_centre', '', True, '4G'),
    ])
    table('routes', ['from_facility_id', 'to_facility_id', 'road_km', 'typical_travel_hours'], [
        ('RBTC-A', 'HSP-R', 10, 0.5), ('RBTC-B', 'HSP-R', 20, 1.0)])
    table('daily_stock', ['date', 'facility_id', 'component', 'blood_group', 'units_in_stock_end_of_day'], [
        (day, facility, 'RBC', 'A+', units) for day in ('2026-03-08', '2026-03-09')
        for facility, units in [('HSP-R', 0), ('RBTC-A', 10), ('RBTC-B', 10)]])
    table('units', ['unit_id', 'component', 'current_facility_id', 'blood_group', 'collection_date', 'expiry_date', 'status_date', 'status'], [
        ('U1', 'RBC', 'RBTC-A', 'A+', '2026-02-20', '2026-03-20', '', 'in_stock'),
        ('U2', 'RBC', 'RBTC-B', 'A+', '2026-02-20', '2026-03-20', '', 'in_stock'),
    ])
    table('requests', REQUEST_COLUMNS, [])
    table('transfers', ['transfer_id', 'request_id', 'unit_id', 'from_facility_id', 'to_facility_id', 'transfer_type', 'dispatched_at', 'received_at'], [])
    return root

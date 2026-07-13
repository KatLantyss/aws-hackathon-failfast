// Reference data sourced directly from backend/data/Vessel_Reference.csv,
// Maintenance_Log.csv and UWI_Inspections.csv (values copied verbatim).
// Noon report time series are synthetically generated (see noonReports.ts)
// since the real Noon_Report.csv has 5,800+ rows and this frontend milestone
// only needs to exercise the UI against realistically-shaped mock data.

export interface VesselRef {
  name: string
  imo: string
  vesselType: string
  teuCapacity: number
  builtYear: number
  flag: string
  classSociety: string
  mainEngineModel: string
  mcrKw: number
  ncrKw: number
  designSpeedKt: number
  designDraftM: number
  designSfocGkWh: number
  hullPaintType: string
  hullPaintAppliedDate: string
  lastDrydockDate: string
  nextDrydockDue: string
  tradeRoute: string
  /** Illustrative baseline laden daily fuel consumption at NCR (MT/day), hand-tuned per hull size to stay in the same order of magnitude as Noon_Report.csv samples. */
  baselineDailyFuelMt: number
}

export const VESSEL_REFS: VesselRef[] = [
  {
    name: 'YM WELLNESS',
    imo: '9786654',
    vesselType: 'Container',
    teuCapacity: 14000,
    builtYear: 2021,
    flag: 'Panama',
    classSociety: 'NK',
    mainEngineModel: 'MAN B&W 9G90ME-C10.5',
    mcrKw: 52620,
    ncrKw: 44730,
    designSpeedKt: 22.5,
    designDraftM: 14.5,
    designSfocGkWh: 165,
    hullPaintType: 'Self-Polishing Copolymer (SPC)',
    hullPaintAppliedDate: '2023-04-10',
    lastDrydockDate: '2023-04-10',
    nextDrydockDue: '2026-04-10',
    tradeRoute: 'Asia-Europe (FE3)',
    baselineDailyFuelMt: 155,
  },
  {
    name: 'YM VICTORY',
    imo: '9695123',
    vesselType: 'Container',
    teuCapacity: 8500,
    builtYear: 2016,
    flag: 'Taiwan',
    classSociety: 'CR',
    mainEngineModel: 'MAN B&W 8G70ME-C9.5',
    mcrKw: 34320,
    ncrKw: 29170,
    designSpeedKt: 21,
    designDraftM: 13,
    designSfocGkWh: 172,
    hullPaintType: 'Silicone Fouling Release',
    hullPaintAppliedDate: '2022-11-02',
    lastDrydockDate: '2022-11-02',
    nextDrydockDue: '2025-11-02',
    tradeRoute: 'Trans-Pacific (PN2)',
    baselineDailyFuelMt: 95,
  },
  {
    name: 'YM COSMOS',
    imo: '9567788',
    vesselType: 'Container',
    teuCapacity: 6500,
    builtYear: 2013,
    flag: 'Panama',
    classSociety: 'NK',
    mainEngineModel: 'MAN B&W 7S80ME-C9',
    mcrKw: 27300,
    ncrKw: 23200,
    designSpeedKt: 20,
    designDraftM: 12.5,
    designSfocGkWh: 178,
    hullPaintType: 'Self-Polishing Copolymer (SPC)',
    hullPaintAppliedDate: '2021-09-15',
    lastDrydockDate: '2021-09-15',
    nextDrydockDue: '2026-09-15',
    tradeRoute: 'Intra-Asia (CIS)',
    baselineDailyFuelMt: 68,
  },
  {
    name: 'YM ESSENCE',
    imo: '9832105',
    vesselType: 'Container',
    teuCapacity: 14200,
    builtYear: 2022,
    flag: 'Panama',
    classSociety: 'NK',
    mainEngineModel: 'MAN B&W 9G90ME-C10.5',
    mcrKw: 52620,
    ncrKw: 44730,
    designSpeedKt: 22.5,
    designDraftM: 14.5,
    designSfocGkWh: 163.5,
    hullPaintType: 'Self-Polishing Copolymer (SPC)',
    hullPaintAppliedDate: '2022-06-20',
    lastDrydockDate: '2022-06-20',
    nextDrydockDue: '2027-06-20',
    tradeRoute: 'Asia-Europe (FE3)',
    baselineDailyFuelMt: 150,
  },
  {
    name: 'YM EVOLUTION',
    imo: '9701344',
    vesselType: 'Container',
    teuCapacity: 8500,
    builtYear: 2017,
    flag: 'Taiwan',
    classSociety: 'CR',
    mainEngineModel: 'MAN B&W 8G70ME-C9.5',
    mcrKw: 34320,
    ncrKw: 29170,
    designSpeedKt: 21,
    designDraftM: 13,
    designSfocGkWh: 171,
    hullPaintType: 'Silicone Fouling Release',
    hullPaintAppliedDate: '2020-05-08',
    lastDrydockDate: '2020-05-08',
    nextDrydockDue: '2025-05-08',
    tradeRoute: 'Trans-Pacific (PN2)',
    baselineDailyFuelMt: 92,
  },
]

export interface MaintenanceEvent {
  id: string
  vessel: string
  imo: string
  date: string
  type: 'Hull Cleaning' | 'Propeller Polishing'
  port: string
  method: string
  vendor: string
  costUsd: number
  downtimeHours: number
}

// Copied verbatim from backend/data/Maintenance_Log.csv
export const MAINTENANCE_LOG: MaintenanceEvent[] = [
  { id: 'MNT-0007', vessel: 'YM COSMOS', imo: '9567788', date: '2022-09-26', type: 'Hull Cleaning', port: 'Colombo', method: 'Diver-assisted brushing', vendor: 'HullWiper', costUsd: 31440, downtimeHours: 7.9 },
  { id: 'MNT-0008', vessel: 'YM COSMOS', imo: '9567788', date: '2023-05-31', type: 'Hull Cleaning', port: 'Ningbo', method: 'In-water grooming', vendor: 'HullWiper', costUsd: 44122, downtimeHours: 9.9 },
  { id: 'MNT-0009', vessel: 'YM COSMOS', imo: '9567788', date: '2023-05-31', type: 'Propeller Polishing', port: 'Rotterdam', method: 'Blade polishing (in-water)', vendor: 'HullWiper', costUsd: 11463, downtimeHours: 4.8 },
  { id: 'MNT-0010', vessel: 'YM COSMOS', imo: '9567788', date: '2024-05-28', type: 'Hull Cleaning', port: 'Rotterdam', method: 'In-water ROV cleaning', vendor: 'Fleetcleaner', costUsd: 33241, downtimeHours: 11.2 },
  { id: 'MNT-0011', vessel: 'YM ESSENCE', imo: '9832105', date: '2023-06-08', type: 'Hull Cleaning', port: 'Fujairah', method: 'In-water ROV cleaning', vendor: 'HullWiper', costUsd: 38731, downtimeHours: 15.7 },
  { id: 'MNT-0012', vessel: 'YM ESSENCE', imo: '9832105', date: '2023-06-16', type: 'Propeller Polishing', port: 'Ningbo', method: 'Blade polishing (in-water)', vendor: 'Propspeed Services', costUsd: 12114, downtimeHours: 4.8 },
  { id: 'MNT-0013', vessel: 'YM ESSENCE', imo: '9832105', date: '2024-06-04', type: 'Hull Cleaning', port: 'Fujairah', method: 'In-water ROV cleaning', vendor: 'Armach Robotics', costUsd: 18198, downtimeHours: 15.4 },
  { id: 'MNT-0014', vessel: 'YM ESSENCE', imo: '9832105', date: '2025-04-24', type: 'Hull Cleaning', port: 'Fujairah', method: 'In-water ROV cleaning', vendor: 'Armach Robotics', costUsd: 33002, downtimeHours: 12.8 },
  { id: 'MNT-0015', vessel: 'YM ESSENCE', imo: '9832105', date: '2025-04-28', type: 'Propeller Polishing', port: 'Colombo', method: 'Blade polishing (in-water)', vendor: 'Propspeed Services', costUsd: 14714, downtimeHours: 6.8 },
  { id: 'MNT-0016', vessel: 'YM EVOLUTION', imo: '9701344', date: '2021-06-05', type: 'Hull Cleaning', port: 'Kaohsiung', method: 'In-water ROV cleaning', vendor: 'Armach Robotics', costUsd: 33514, downtimeHours: 12.6 },
  { id: 'MNT-0017', vessel: 'YM EVOLUTION', imo: '9701344', date: '2022-05-25', type: 'Hull Cleaning', port: 'Fujairah', method: 'In-water ROV cleaning', vendor: 'Subsea Global Solutions', costUsd: 18832, downtimeHours: 11.2 },
  { id: 'MNT-0018', vessel: 'YM EVOLUTION', imo: '9701344', date: '2022-05-27', type: 'Propeller Polishing', port: 'Rotterdam', method: 'Blade polishing (in-water)', vendor: 'HullWiper', costUsd: 20094, downtimeHours: 5.4 },
  { id: 'MNT-0019', vessel: 'YM EVOLUTION', imo: '9701344', date: '2023-06-16', type: 'Hull Cleaning', port: 'Singapore', method: 'In-water grooming', vendor: 'HullWiper', costUsd: 42776, downtimeHours: 13.9 },
  { id: 'MNT-0020', vessel: 'YM EVOLUTION', imo: '9701344', date: '2024-04-03', type: 'Hull Cleaning', port: 'Kaohsiung', method: 'In-water grooming', vendor: 'Armach Robotics', costUsd: 35936, downtimeHours: 10.9 },
  { id: 'MNT-0021', vessel: 'YM EVOLUTION', imo: '9701344', date: '2025-01-25', type: 'Hull Cleaning', port: 'Colombo', method: 'Diver-assisted brushing', vendor: 'Fleetcleaner', costUsd: 20865, downtimeHours: 14.7 },
  { id: 'MNT-0004', vessel: 'YM VICTORY', imo: '9695123', date: '2023-10-23', type: 'Hull Cleaning', port: 'Rotterdam', method: 'In-water grooming', vendor: 'Subsea Global Solutions', costUsd: 29972, downtimeHours: 8.7 },
  { id: 'MNT-0005', vessel: 'YM VICTORY', imo: '9695123', date: '2024-11-25', type: 'Hull Cleaning', port: 'Singapore', method: 'In-water grooming', vendor: 'Armach Robotics', costUsd: 25472, downtimeHours: 15.1 },
  { id: 'MNT-0006', vessel: 'YM VICTORY', imo: '9695123', date: '2024-12-01', type: 'Propeller Polishing', port: 'Singapore', method: 'Blade polishing (in-water)', vendor: 'HullWiper', costUsd: 14793, downtimeHours: 8.7 },
  { id: 'MNT-0001', vessel: 'YM WELLNESS', imo: '9786654', date: '2023-12-22', type: 'Hull Cleaning', port: 'Fujairah', method: 'Diver-assisted brushing', vendor: 'HullWiper', costUsd: 29691, downtimeHours: 14.4 },
  { id: 'MNT-0002', vessel: 'YM WELLNESS', imo: '9786654', date: '2023-12-30', type: 'Propeller Polishing', port: 'Kaohsiung', method: 'Blade polishing (in-water)', vendor: 'HullWiper', costUsd: 18564, downtimeHours: 8.7 },
  { id: 'MNT-0003', vessel: 'YM WELLNESS', imo: '9786654', date: '2025-01-02', type: 'Hull Cleaning', port: 'Kaohsiung', method: 'In-water ROV cleaning', vendor: 'Armach Robotics', costUsd: 30160, downtimeHours: 10.4 },
]

export interface UwiInspection {
  id: string
  vessel: string
  imo: string
  date: string
  port: string
  surveyor: string
  method: string
  biofoulingScore: number
  conditionRating: string
  paintBreakdownPct: number
  propellerCondition: string
  cleaningRecommended: string
  notes: string
}

// Copied verbatim from backend/data/UWI_Inspections.csv
export const UWI_INSPECTIONS: UwiInspection[] = [
  { id: 'UWI-0001', vessel: 'YM WELLNESS', imo: '9786654', date: '2023-08-12', port: 'Ningbo', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 26, conditionRating: 'MODERATE', paintBreakdownPct: 6.2, propellerCondition: 'Fair', cleaningRecommended: 'NO', notes: 'Predominantly slime with light barnacle clusters on flat bottom.' },
  { id: 'UWI-0002', vessel: 'YM WELLNESS', imo: '9786654', date: '2024-01-20', port: 'Hamburg', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 43, conditionRating: 'MODERATE', paintBreakdownPct: 8.8, propellerCondition: 'Good', cleaningRecommended: 'YES', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0003', vessel: 'YM WELLNESS', imo: '9786654', date: '2024-07-11', port: 'Rotterdam', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 82, conditionRating: 'SEVERE', paintBreakdownPct: 14.7, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0004', vessel: 'YM WELLNESS', imo: '9786654', date: '2025-01-30', port: 'Colombo', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 17.4, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0005', vessel: 'YM VICTORY', imo: '9695123', date: '2023-01-09', port: 'Ningbo', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 18, conditionRating: 'LIGHT', paintBreakdownPct: 4.2, propellerCondition: 'Good', cleaningRecommended: 'NO', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0006', vessel: 'YM VICTORY', imo: '9695123', date: '2023-07-18', port: 'Colombo', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 49, conditionRating: 'HEAVY', paintBreakdownPct: 9.8, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'YES - PRIORITY', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0007', vessel: 'YM VICTORY', imo: '9695123', date: '2024-01-14', port: 'Kaohsiung', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 69, conditionRating: 'SEVERE', paintBreakdownPct: 13.8, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0008', vessel: 'YM VICTORY', imo: '9695123', date: '2024-07-11', port: 'Singapore', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 89, conditionRating: 'SEVERE', paintBreakdownPct: 15.3, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0009', vessel: 'YM VICTORY', imo: '9695123', date: '2024-12-15', port: 'Kaohsiung', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 25.4, propellerCondition: 'Fair', cleaningRecommended: 'YES - PRIORITY', notes: 'Fouling within normal range for time since drydock, monitor next cycle.' },
  { id: 'UWI-0010', vessel: 'YM COSMOS', imo: '9567788', date: '2022-01-08', port: 'Singapore', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 21, conditionRating: 'LIGHT', paintBreakdownPct: 5.6, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'NO', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0011', vessel: 'YM COSMOS', imo: '9567788', date: '2022-06-11', port: 'Hamburg', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 44, conditionRating: 'MODERATE', paintBreakdownPct: 10.8, propellerCondition: 'Fair', cleaningRecommended: 'YES', notes: 'Fouling within normal range for time since drydock, monitor next cycle.' },
  { id: 'UWI-0012', vessel: 'YM COSMOS', imo: '9567788', date: '2022-12-15', port: 'Ningbo', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 62, conditionRating: 'HEAVY', paintBreakdownPct: 13.4, propellerCondition: 'Fair', cleaningRecommended: 'YES - PRIORITY', notes: 'Heavy barnacle fouling concentrated on port side and bilge keel.' },
  { id: 'UWI-0013', vessel: 'YM COSMOS', imo: '9567788', date: '2023-06-02', port: 'Singapore', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 13.7, propellerCondition: 'Fair', cleaningRecommended: 'YES - PRIORITY', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0014', vessel: 'YM COSMOS', imo: '9567788', date: '2023-11-21', port: 'Singapore', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 22.8, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'YES - PRIORITY', notes: 'Heavy barnacle fouling concentrated on port side and bilge keel.' },
  { id: 'UWI-0015', vessel: 'YM COSMOS', imo: '9567788', date: '2024-06-23', port: 'Kaohsiung', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 21.7, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0016', vessel: 'YM COSMOS', imo: '9567788', date: '2024-11-29', port: 'Colombo', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 34.8, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0017', vessel: 'YM ESSENCE', imo: '9832105', date: '2022-11-12', port: 'Colombo', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 28, conditionRating: 'MODERATE', paintBreakdownPct: 5.7, propellerCondition: 'Poor - erosion noted', cleaningRecommended: 'YES', notes: 'Predominantly slime with light barnacle clusters on flat bottom.' },
  { id: 'UWI-0018', vessel: 'YM ESSENCE', imo: '9832105', date: '2023-04-22', port: 'Singapore', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 48, conditionRating: 'HEAVY', paintBreakdownPct: 12.1, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'YES - PRIORITY', notes: 'Predominantly slime with light barnacle clusters on flat bottom.' },
  { id: 'UWI-0019', vessel: 'YM ESSENCE', imo: '9832105', date: '2023-11-10', port: 'Ningbo', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 88, conditionRating: 'SEVERE', paintBreakdownPct: 14.6, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Predominantly slime with light barnacle clusters on flat bottom.' },
  { id: 'UWI-0020', vessel: 'YM ESSENCE', imo: '9832105', date: '2024-06-01', port: 'Kaohsiung', surveyor: 'ClassNK Underwater Survey', method: 'Diver Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 14.7, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'YES - PRIORITY', notes: 'Heavy barnacle fouling concentrated on port side and bilge keel.' },
  { id: 'UWI-0021', vessel: 'YM ESSENCE', imo: '9832105', date: '2024-11-16', port: 'Ningbo', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 17.8, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'YES - PRIORITY', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0022', vessel: 'YM ESSENCE', imo: '9832105', date: '2025-04-25', port: 'Colombo', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 32.2, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Heavy barnacle fouling concentrated on port side and bilge keel.' },
  { id: 'UWI-0023', vessel: 'YM EVOLUTION', imo: '9701344', date: '2020-10-04', port: 'Rotterdam', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 33, conditionRating: 'MODERATE', paintBreakdownPct: 5.6, propellerCondition: 'Good', cleaningRecommended: 'YES', notes: 'Fouling within normal range for time since drydock, monitor next cycle.' },
  { id: 'UWI-0024', vessel: 'YM EVOLUTION', imo: '9701344', date: '2021-03-15', port: 'Singapore', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 43, conditionRating: 'MODERATE', paintBreakdownPct: 8.2, propellerCondition: 'Fair', cleaningRecommended: 'YES', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0025', vessel: 'YM EVOLUTION', imo: '9701344', date: '2021-10-15', port: 'Rotterdam', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 80, conditionRating: 'SEVERE', paintBreakdownPct: 17.2, propellerCondition: 'Fair - light roughness', cleaningRecommended: 'YES - PRIORITY', notes: 'Predominantly slime with light barnacle clusters on flat bottom.' },
  { id: 'UWI-0026', vessel: 'YM EVOLUTION', imo: '9701344', date: '2022-03-19', port: 'Rotterdam', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 83, conditionRating: 'SEVERE', paintBreakdownPct: 22.7, propellerCondition: 'Fair', cleaningRecommended: 'YES - PRIORITY', notes: 'Predominantly slime with light barnacle clusters on flat bottom.' },
  { id: 'UWI-0027', vessel: 'YM EVOLUTION', imo: '9701344', date: '2022-10-23', port: 'Kaohsiung', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 29.3, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0028', vessel: 'YM EVOLUTION', imo: '9701344', date: '2023-05-28', port: 'Kaohsiung', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 30.3, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Fouling within normal range for time since drydock, monitor next cycle.' },
  { id: 'UWI-0029', vessel: 'YM EVOLUTION', imo: '9701344', date: '2023-12-14', port: 'Singapore', surveyor: 'BV Marine', method: 'ROV Survey (Diver-assisted)', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 34.5, propellerCondition: 'Poor - erosion noted', cleaningRecommended: 'YES - PRIORITY', notes: 'Propeller leading edge shows minor erosion, no urgent action required.' },
  { id: 'UWI-0030', vessel: 'YM EVOLUTION', imo: '9701344', date: '2024-07-02', port: 'Kaohsiung', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 26.1, propellerCondition: 'Good', cleaningRecommended: 'YES - PRIORITY', notes: 'Antifouling breakdown approaching threshold, recommend recoating at next drydock.' },
  { id: 'UWI-0031', vessel: 'YM EVOLUTION', imo: '9701344', date: '2024-12-19', port: 'Rotterdam', surveyor: 'Subsea Compliance Ltd.', method: 'ROV Survey', biofoulingScore: 95, conditionRating: 'SEVERE', paintBreakdownPct: 41.7, propellerCondition: 'Fair', cleaningRecommended: 'YES - PRIORITY', notes: 'Heavy barnacle fouling concentrated on port side and bilge keel.' },
]

/** Illustrative current position + status, placed along each vessel's real trade route. Would come from an AIS feed in production. */
export const VESSEL_LIVE_STATE: Record<
  string,
  { lat: number; lon: number; headingDeg: number; speedKt: number; status: 'underway' | 'moored' | 'anchored'; currentPort: string | null; destinationPort: string | null }
> = {
  '9786654': { lat: 22.9, lon: 113.9, headingDeg: 128, speedKt: 19.8, status: 'underway', currentPort: null, destinationPort: 'Singapore' },
  '9695123': { lat: 34.6, lon: -145.2, headingDeg: 72, speedKt: 18.1, status: 'underway', currentPort: null, destinationPort: 'Long Beach' },
  '9567788': { lat: 1.29, lon: 103.85, headingDeg: 0, speedKt: 0, status: 'moored', currentPort: 'Singapore', destinationPort: null },
  '9832105': { lat: 51.95, lon: 4.05, headingDeg: 205, speedKt: 0.4, status: 'anchored', currentPort: null, destinationPort: 'Rotterdam' },
  '9701344': { lat: 22.6, lon: 120.28, headingDeg: 340, speedKt: 0, status: 'moored', currentPort: 'Kaohsiung', destinationPort: null },
}

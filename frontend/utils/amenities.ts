// Mirrors app/models/apartment.py's AmenityType enum values. Shared between
// the owner panel's apartment form and the public apartment listing so the
// list of amenities only lives in one place.
export const AMENITY_TYPES = [
  'wifi',
  'electric_heating',
  'fan',
  'tv',
  'equipped_kitchen',
  'microwave',
  'toaster',
  'dishwasher',
  'coffee_maker',
  'hair_dryer',
  'terrace',
  'elevator',
  'pets_allowed',
  'no_smoking',
  'shared_laundry',
] as const

export type AmenityType = (typeof AMENITY_TYPES)[number]

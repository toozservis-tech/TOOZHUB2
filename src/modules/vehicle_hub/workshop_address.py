"""Registered office stays billing data; only a confirmed workshop is discoverable."""
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

ADDRESS_FIELDS = ('street', 'street_number', 'city', 'zip')


class WorkshopAddressInput(BaseModel):
    workshop_same_as_registered: bool | None = None
    workshop_street: str | None = Field(default=None, max_length=200)
    workshop_street_number: str | None = Field(default=None, max_length=64)
    workshop_city: str | None = Field(default=None, max_length=120)
    workshop_zip: str | None = Field(default=None, max_length=32)

    @model_validator(mode='after')
    def complete_separate_address(self):
        if self.workshop_same_as_registered is False:
            if any(not str(getattr(self, 'workshop_' + k) or '').strip() for k in ('street', 'city', 'zip')):
                raise ValueError('Vyplňte ulici, město a PSČ provozovny.')
        return self


def apply_workshop_address(row, payload):
    choice = getattr(payload, 'workshop_same_as_registered', None)
    if choice is None:
        return  # An older client cannot silently declare a virtual office a workshop.
    fields = {k: str(getattr(payload, 'workshop_' + k, None) or '').strip() or None for k in ADDRESS_FIELDS}
    if choice:
        fields = {k: str(getattr(row, k, None) or '').strip() or None for k in ADDRESS_FIELDS}
    if any(not fields[k] for k in ('street', 'city', 'zip')):
        raise HTTPException(422, 'Vyplňte úplnou adresu provozovny.')
    row.workshop_same_as_registered = choice
    for key, value in fields.items():
        setattr(row, 'workshop_' + key, value)


def workshop_fields(row):
    if row.workshop_same_as_registered is None:
        # Legacy location is unconfirmed: no distance calculated from the office.
        return {k: None for k in ADDRESS_FIELDS}
    prefix = '' if row.workshop_same_as_registered else 'workshop_'
    return {k: getattr(row, prefix + k, None) for k in ADDRESS_FIELDS}

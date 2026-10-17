"""Care administration capability packs and runnable, session-only program generation.

Does not train weights, export resident records, call providers or mutate production.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Module = Literal['office', 'accounting', 'benefit', 'food_inventory', 'supplies_inventory']
CAPABILITIES = {
    'office': {'title': '사무·일정', 'entities': ['task', 'due_date', 'assignee_code', 'status'],
               'checks': ['due-date format', 'completion evidence'],
               'outputs': ['task register', 'open-task summary']},
    'accounting': {'title': '회계·증빙', 'entities': ['income_expense', 'amount_krw', 'evidence_ref'],
                   'checks': ['positive integer KRW', 'evidence required'],
                   'outputs': ['cash register', 'income and expense totals'],
                   'external_submission': False},
    'benefit': {'title': '요양급여 검토 초안',
                'entities': ['resident_code', 'month', 'days', 'verified_daily_fee',
                             'verified_copay_percent', 'rate_evidence', 'noncovered_amount'],
                'checks': ['no names or national IDs', 'unique resident/month',
                           'calendar-day bounds', 'capacity limit', 'manual rate evidence'],
                'outputs': ['draft gross', 'draft insurer share', 'draft resident share'],
                'external_submission': False, 'statutory_rate_lookup': False},
    'food_inventory': {'title': '식자재 수불',
                       'entities': ['item_code', 'lot', 'unit', 'expiry', 'movement'],
                       'checks': ['no negative lot stock', 'stable unit', 'expiry review'],
                       'outputs': ['lot balance', 'expiry check']},
    'supplies_inventory': {'title': '기타 재고',
                           'entities': ['item_code', 'lot', 'unit', 'movement'],
                           'checks': ['no negative lot stock', 'stable unit'],
                           'outputs': ['lot balance', 'reorder check']},
}


class CareOperationsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    brand: str = Field(default='해온', min_length=1, max_length=40)
    floor: Literal['3'] = '3'
    capacity: int = Field(default=49, ge=1, le=300)
    modules: list[Module] = Field(default_factory=lambda: list(CAPABILITIES), min_length=1,
                                  max_length=5)
    confirmed_digest: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def unique_modules(self):
        if len(set(self.modules)) != len(self.modules):
            raise ValueError('duplicate modules')
        if not self.brand.strip():
            raise ValueError('brand required')
        return self


def build_operations_program(request: CareOperationsRequest) -> dict[str, object]:
    config = request.model_dump(exclude={'confirmed_digest'})
    config['modules'] = sorted(config['modules'])
    canonical = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    packet: dict[str, object] = {
        'schema_version': 'apf.care-operations/v1', 'digest': digest, 'configuration': config,
        'capabilities': {key: CAPABILITIES[key] for key in config['modules']},
        'status': 'CONFIRMATION_REQUIRED', 'artifact': None,
        'runtime': 'single HTML; session memory; explicit JSON export; no provider calls',
        'legal_compliance': 'NOT_VERIFIED', 'production_change_allowed': False,
        'model_weights_updated': False, 'external_submission': False,
        'deployment_requirements': ['server authentication and floor scope',
                                    'durable access-controlled records and backups',
                                    'verified current fee schedules',
                                    'operator acceptance and production review'],
    }
    if request.confirmed_digest != digest:
        if request.confirmed_digest:
            packet['status'] = 'CONFIRMATION_STALE'
        return packet
    # JSON in a script element must not close the element or introduce HTML.
    safe = canonical.replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026')
    template = Path(__file__).with_name('care_operations_program.html').read_text(encoding='utf-8')
    content = template.replace('__APF_CONFIG_JSON__', safe)
    packet.update(status='PROGRAM_READY', artifact={
        'filename': 'haeon-operations-preview.html', 'media_type': 'text/html;charset=utf-8',
        'sha256': hashlib.sha256(content.encode()).hexdigest(), 'content': content,
    })
    return packet

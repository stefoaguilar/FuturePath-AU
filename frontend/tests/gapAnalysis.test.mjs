
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { requestGapAnalysis } from '../src/gapAnalysis.js';

const records = JSON.parse(
  readFileSync(
    new URL('../../data/opportunities.json', import.meta.url),
    'utf8'
  )
).opportunities;

const opportunity = records.find(
  (record) => record.id === 'OPP-003'
);

function result(conditionId, status) {
  const condition = opportunity.eligibility_conditions.find(
    (item) => item.id === conditionId
  );

  return {
    condition_id: condition.id,
    status,
    explanation: 'Verified backend explanation.',
    requirement: condition.text,
    evidence_summary: condition.evidence_summary,
    source_url: condition.source_url
  };
}

function payload() {
  return {
    opportunity_id: opportunity.id,
    confirmed_unmet_requirements: [
      result('OPP-003-E2', 'unmet')
    ],
    requirements_needing_review: [
      result('OPP-003-E1', 'uncertain')
    ],
    skills_to_explore: [
      'computing',
      'software engineering'
    ],
    source_url: opportunity.source_url,
    notice: 'Advisory skills do not establish ineligibility.'
  };
}

const respondingWith = (data, ok = true) => async () => ({
  ok,
  json: async () => data
});

test(
  'accepts published gap results and excludes identity from the request',
  async () => {
    let requestUrl;
    let requestOptions;

    const output = await requestGapAnalysis(
      opportunity,
      {
        citizenship_status: 'nz_citizen',
        skills: ['cyber security'],
        identity_answer: 'yes'
      },
      {
        fetchImpl: async (url, options) => {
          requestUrl = url;
          requestOptions = options;

          return {
            ok: true,
            json: async () => payload()
          };
        }
      }
    );

    assert.equal(
      requestUrl,
      'http://127.0.0.1:8000/api/gaps/analyse'
    );

    assert.equal(requestOptions.method, 'POST');

    assert.deepEqual(JSON.parse(requestOptions.body), {
      opportunity_id: 'OPP-003',
      profile: {
        citizenship_status: 'nz_citizen',
        skills: ['cyber security']
      }
    });

    assert.equal(
      output.confirmed_unmet_requirements[0].condition_id,
      'OPP-003-E2'
    );

    assert.equal(
      output.requirements_needing_review[0].status,
      'uncertain'
    );
  }
);

test(
  'rejects mismatched evidence, automated identity decisions, duplicate results, and invented skills',
  async () => {
    const badPayloads = [];

    const wrongSource = payload();
    wrongSource.source_url = 'https://example.org';
    badPayloads.push(wrongSource);

    const identityDecision = payload();
    identityDecision.requirements_needing_review[0].status = 'satisfied';
    badPayloads.push(identityDecision);

    const duplicate = payload();
    duplicate.confirmed_unmet_requirements.push(
      result('OPP-003-E2', 'unmet')
    );
    badPayloads.push(duplicate);

    const fabricatedEvidence = payload();
    fabricatedEvidence.confirmed_unmet_requirements[0].source_url =
      'https://example.org';
    badPayloads.push(fabricatedEvidence);

    const inventedSkill = payload();
    inventedSkill.skills_to_explore.push(
      'invented qualification'
    );
    badPayloads.push(inventedSkill);

    for (const badPayload of badPayloads) {
      await assert.rejects(
        requestGapAnalysis(
          opportunity,
          {},
          { fetchImpl: respondingWith(badPayload) }
        )
      );
    }
  }
);

test(
  'rejects unsuccessful HTTP responses without accepting gap results',
  async () => {
    await assert.rejects(
      requestGapAnalysis(
        opportunity,
        {},
        { fetchImpl: respondingWith(payload(), false) }
      ),
      /Gap-analysis service unavailable/
    );
  }
);

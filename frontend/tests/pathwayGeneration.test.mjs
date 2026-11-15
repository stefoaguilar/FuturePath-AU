
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { requestDraftPathway } from '../src/pathwayGeneration.js';

const opportunities = JSON.parse(
  readFileSync(
    new URL('../../data/opportunities.json', import.meta.url),
    'utf8'
  )
).opportunities;

const opportunity = opportunities.find(
  (record) => record.id === 'OPP-003'
);

function requirementStep(id, status) {
  const condition = opportunity.eligibility_conditions.find(
    (item) => item.id === id
  );

  const identity = condition.type === 'identity_requirement';

  return {
    step_id: `requirement:${id}`,
    category: status === 'unmet'
      ? 'requirement_review'
      : 'human_review',
    title: identity
      ? 'Review the published identity requirement'
      : status === 'unmet'
        ? 'Review a potentially unmet requirement'
        : 'Check an uncertain requirement',
    description: condition.text,
    explanation: identity
      ? 'Identity requires voluntary personal review.'
      : 'Review the published requirement with the provider.',
    eligibility_status: status,
    source_url: condition.source_url,
    editable: true
  };
}

function draft() {
  return {
    opportunity_id: opportunity.id,
    opportunity_title: opportunity.title,
    reference_date: '2026-11-15',
    status: 'draft',
    approved: false,
    can_export: false,
    steps: [
      requirementStep('OPP-003-E1', 'uncertain'),
      requirementStep('OPP-003-E2', 'unmet'),
      requirementStep('OPP-003-E3', 'uncertain'),
      requirementStep('OPP-003-E5', 'uncertain'),
      requirementStep('OPP-003-E6', 'uncertain'),

      ...opportunity.skills.map((skill, index) => ({
        step_id: `skill:${index + 1}`,
        category: 'skill_exploration',
        title: `Explore ${skill}`,
        description: `Consider exploring ${skill}.`,
        explanation: 'Advisory only, not a confirmed deficiency.',
        eligibility_status: null,
        source_url: opportunity.source_url,
        editable: true
      })),

      {
        step_id: 'deadline:review',
        category: 'deadline_review',
        title: 'Check for a future application round',
        description: 'The source record reports this application round as closed.',
        explanation: 'Confirm current application dates with the provider.',
        deadline_classification: 'reported_closed',
        deadline_date: '2026-02-25',
        days_until_deadline: null,
        deadline_note: opportunity.deadline.note,
        source_url: opportunity.source_url,
        editable: true
      },

      {
        step_id: 'source:verify',
        category: 'source_verification',
        title: 'Review the official opportunity information',
        description: 'Check the official published conditions.',
        explanation: 'Published information can change.',
        source_url: opportunity.source_url,
        editable: true
      }
    ],
    notice: 'This is an unapproved student-editable informational draft.'
  };
}

const reply = (data, ok = true) => async () => ({
  ok,
  json: async () => data
});

test(
  'accepts 12 source-backed draft steps and excludes identity from the request',
  async () => {
    let url;
    let options;

    const result = await requestDraftPathway(
      opportunity,
      {
        citizenship_status: 'nz_citizen',
        weighted_average: 65,
        skills: [],
        identity_answer: 'yes'
      },
      {
        fetchImpl: async (requestUrl, requestOptions) => {
          url = requestUrl;
          options = requestOptions;

          return {
            ok: true,
            json: async () => draft()
          };
        }
      }
    );

    assert.equal(
      url,
      'http://127.0.0.1:8000/api/pathways/generate'
    );

    assert.equal(options.method, 'POST');

    assert.deepEqual(JSON.parse(options.body), {
      opportunity_id: 'OPP-003',
      profile: {
        citizenship_status: 'nz_citizen',
        weighted_average: 65,
        skills: []
      }
    });

    assert.equal(result.steps.length, 12);
    assert.equal(result.status, 'draft');
    assert.equal(result.approved, false);
    assert.equal(result.can_export, false);

    assert.equal(
      result.steps.find(
        (step) => step.step_id === 'deadline:review'
      ).title,
      'Check for a future application round'
    );
  }
);

test(
  'rejects fabricated requirements, source links and identity decisions',
  async () => {
    const modifications = [
      (data) => {
        data.steps[0].eligibility_status = 'unmet';
      },
      (data) => {
        data.steps[1].description = 'Invented requirement';
      },
      (data) => {
        data.steps[1].source_url = 'https://example.org/fake';
      },
      (data) => {
        data.steps[1].step_id = 'requirement:OPP-999-E1';
      },
      (data) => {
        data.steps[1].category = 'human_review';
      }
    ];

    for (const change of modifications) {
      const data = draft();
      change(data);

      await assert.rejects(
        requestDraftPathway(
          opportunity,
          {},
          { fetchImpl: reply(data) }
        )
      );
    }
  }
);

test(
  'rejects unapproved-status changes, invented skills and incomplete drafts',
  async () => {
    const modifications = [
      (data) => {
        data.status = 'approved';
      },
      (data) => {
        data.approved = true;
      },
      (data) => {
        data.can_export = true;
      },
      (data) => {
        data.opportunity_title = 'Wrong opportunity';
      },
      (data) => {
        data.steps[5].title = 'Explore invented skill';
      },
      (data) => {
        data.steps.push({ ...data.steps[0] });
      },
      (data) => {
        data.steps = data.steps.filter(
          (step) => step.step_id !== 'deadline:review'
        );
      },
      (data) => {
        data.steps = data.steps.filter(
          (step) => step.step_id !== 'source:verify'
        );
      },
      (data) => {
        data.steps[0].editable = false;
      }
    ];

    for (const change of modifications) {
      const data = draft();
      change(data);

      await assert.rejects(
        requestDraftPathway(
          opportunity,
          {},
          { fetchImpl: reply(data) }
        )
      );
    }
  }
);

test(
  'rejects unsuccessful HTTP responses and invalid JSON',
  async () => {
    await assert.rejects(
      requestDraftPathway(
        opportunity,
        {},
        { fetchImpl: reply(draft(), false) }
      ),
      /Pathway service unavailable/
    );

    await assert.rejects(
      requestDraftPathway(
        opportunity,
        {},
        {
          fetchImpl: async () => ({
            ok: true,
            json: async () => {
              throw new SyntaxError('Bad JSON');
            }
          })
        }
      ),
      SyntaxError
    );
  }
);


import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { toEditableMilestones } from '../src/pathwayMilestones.js';

const opportunities = JSON.parse(
  readFileSync(
    new URL('../../data/opportunities.json', import.meta.url),
    'utf8'
  )
).opportunities;

const opportunity = opportunities.find(
  (item) => item.id === 'OPP-003'
);

function draft() {
  const requirementSteps = opportunity.eligibility_conditions
    .filter((condition) => condition.id !== 'OPP-003-E4')
    .map((condition) => {
      const unmet = condition.id === 'OPP-003-E2';
      const identity = condition.type === 'identity_requirement';

      return {
        step_id: `requirement:${condition.id}`,
        category: unmet ? 'requirement_review' : 'human_review',
        title: identity
          ? 'Review the published identity requirement'
          : unmet
            ? 'Review a potentially unmet requirement'
            : 'Check an uncertain requirement',
        description: condition.text,
        explanation: identity
          ? 'Requires voluntary personal review, never identity scoring.'
          : 'Review the published criterion with the provider.',
        eligibility_status: unmet ? 'unmet' : 'uncertain',
        source_url: condition.source_url,
        editable: true
      };
    });

  const skills = opportunity.skills.map((skill, index) => ({
    step_id: `skill:${index + 1}`,
    category: 'skill_exploration',
    title: `Explore ${skill}`,
    description: `The provider lists ${skill} as a related skill.`,
    explanation: 'Advisory only, not an eligibility decision.',
    eligibility_status: null,
    source_url: opportunity.source_url,
    editable: true
  }));

  return {
    opportunity_id: opportunity.id,
    opportunity_title: opportunity.title,
    reference_date: '2026-11-15',
    status: 'draft',
    approved: false,
    can_export: false,
    steps: [
      ...requirementSteps,
      ...skills,
      {
        step_id: 'deadline:review',
        category: 'deadline_review',
        title: 'Check for a future application round',
        description: 'The recorded application round is closed.',
        explanation: 'Confirm current dates with the provider.',
        deadline_classification: 'reported_closed',
        deadline_date: '2026-02-25',
        deadline_note: opportunity.deadline.note,
        source_url: opportunity.source_url,
        editable: true
      },
      {
        step_id: 'source:verify',
        category: 'source_verification',
        title: 'Review the official opportunity information',
        description: 'Check the provider information before deciding.',
        explanation: 'Official terms may change.',
        source_url: opportunity.source_url,
        editable: true
      }
    ],
    notice: 'Student approval required.'
  };
}

test(
  'converts all 12 backend steps into unique, editable React milestones',
  () => {
    const source = draft();
    const steps = toEditableMilestones(opportunity, source, 7);

    assert.equal(steps.length, 12);
    assert.equal(new Set(steps.map((step) => step.id)).size, 12);

    assert.deepEqual(
      steps.map((step) => step.id),
      Array.from(
        { length: 12 },
        (_, index) => `backend-7-${index + 1}`
      )
    );

    for (const step of steps) {
      assert.equal(step.status, 'pending');
      assert.equal(step.actionableUrl, '');
      assert.ok(step.phase);
      assert.ok(step.title);
      assert.ok(step.description);
      assert.ok(step.timeline);
      assert.equal(step.sourceUrl, opportunity.source_url);
    }

    assert.notEqual(
      toEditableMilestones(opportunity, source, 8)[0].id,
      steps[0].id
    );
  }
);

test(
  'retains published requirement evidence without treating identity as evaluated',
  () => {
    const steps = toEditableMilestones(opportunity, draft(), 9);

    const identity = steps.find(
      (step) => step.sourceStepId === 'requirement:OPP-003-E1'
    );

    const citizenship = steps.find(
      (step) => step.sourceStepId === 'requirement:OPP-003-E2'
    );

    const condition = opportunity.eligibility_conditions.find(
      (item) => item.id === 'OPP-003-E1'
    );

    assert.equal(identity.eligibilityStatus, 'uncertain');
    assert.equal(identity.sourceCategory, 'human_review');
    assert.equal(identity.sourceConditions[0].text, condition.text);
    assert.equal(
      identity.sourceConditions[0].evidence_summary,
      condition.evidence_summary
    );
    assert.equal(
      identity.sourceConditions[0].source_url,
      condition.source_url
    );

    assert.equal(citizenship.eligibilityStatus, 'unmet');
    assert.equal(citizenship.sourceCategory, 'requirement_review');
    assert.equal(
      citizenship.sourceConditions[0].id,
      'OPP-003-E2'
    );
  }
);

test(
  'keeps skills advisory and closed deadline as a verification action',
  () => {
    const steps = toEditableMilestones(opportunity, draft(), 3);

    const skills = steps.filter(
      (step) => step.sourceCategory === 'skill_exploration'
    );

    assert.equal(skills.length, 5);
    assert.ok(
      skills.every((step) => step.eligibilityStatus === null)
    );

    const deadline = steps.find(
      (step) => step.sourceStepId === 'deadline:review'
    );

    assert.equal(
      deadline.title,
      'Check for a future application round'
    );

    assert.equal(
      deadline.timeline,
      'Verify dates with provider'
    );

    assert.ok(
      deadline.description.includes(opportunity.deadline.note)
    );

    assert.equal(deadline.actionableUrl, '');

    const source = steps.find(
      (step) => step.sourceStepId === 'source:verify'
    );

    assert.equal(source.sourceUrl, opportunity.source_url);
  }
);

test(
  'rejects non-draft or mismatched pathways without mutating source data',
  () => {
    const original = draft();
    const before = JSON.stringify(original);

    const converted = toEditableMilestones(
      opportunity,
      original,
      5
    );

    assert.equal(JSON.stringify(original), before);

    converted[0].sourceConditions[0].text = 'Edited local label';

    assert.equal(
      opportunity.eligibility_conditions[0].text,
      'You must be of Aboriginal and/or Torres Strait Islander descent.'
    );

    const modifications = [
      (data) => { data.opportunity_id = 'OPP-999'; },
      (data) => { data.status = 'approved'; },
      (data) => { data.approved = true; },
      (data) => { data.can_export = true; },
      (data) => { data.steps = null; }
    ];

    for (const change of modifications) {
      const invalid = draft();
      change(invalid);

      assert.throws(
        () => toEditableMilestones(opportunity, invalid, 5),
        /Cannot convert an invalid pathway draft/
      );
    }
  }
);

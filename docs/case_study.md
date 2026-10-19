# Case study: a tapas restaurant in Milan

The restaurant and its figures are anonymised. Real numbers will be added only with the owner's written consent.

## Situation

A small tapas restaurant in Milan sells on Deliveroo, dinner only, Tuesday to Sunday. It averages a few orders a night,
with Friday and Saturday the strongest nights and most orders arriving between 19:00 and 21:00. Empanadas are the anchor
product.

During the pilot, most orders went through a Deliveroo "Marketer" offer and the restaurant also paid for sponsored
placement. Over two months, orders and menu conversion fell. The owner could see orders on the platform dashboard but
not whether the discounts and ads were paying for themselves.

## What we did

1. Collected four months of Partner Hub exports: product sales per fortnight, order-level files with commissions, ad
   performance, customer mix and service-speed reports.
2. Wrote descriptive reports: sales by product and fortnight, time-of-day patterns, commission weight, ad return.
3. Wrote the decision framework in `docs/framework.md` to move from "orders went up" to "the promo made or lost €X".

## What the data could and could not say

- **Could**: which dishes drive revenue, when demand happens, how much of each order the platform keeps, whether ads
  returned more than they cost on attributed sales.
- **Could not**: whether the discounts were profitable. Almost every order was discounted, so there was no clean
  comparison period; food costs per dish were not available; and at a few orders a night, a month of history cannot
  separate a real lift from noise.

## What Promo Profit Lab adds

- The margin and break-even engine turns food cost and commission into the uplift each discount must reach.
- The uplift model compares promo and non-promo nights with honest intervals.
- The test planner showed that at a few orders a night, judging a promo needs weeks of on/off nights, so the right
  recommendation was a pre-committed switchback test rather than a verdict.
- The agent packages all of this into a report the owner can read, and the eval suite shows how often its verdicts are
  right on restaurants where the true effect is known.

## Next step with the owner

Agree food-cost estimates per dish (±20% is enough), then run one switchback test of the current discount, alternating
promo nights within each weekday, with the length set by `plan_experiment`.

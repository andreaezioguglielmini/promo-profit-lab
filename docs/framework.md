# A decision framework for food-delivery promotions

Public summary of the working document behind Promo Profit Lab. Section numbers match the references in the code.

## 1. Problem

Restaurants on delivery platforms run discounts, 2x1s, bundles and free delivery without a way to know whether those
promotions create or destroy money. The platform shows that orders went up; it does not show whether profit did.
Each promo order carries a lower margin, and part of the promo volume would have happened anyway, so **more orders is
not more profit**. Three costs stay invisible:

1. The discount given to customers who would have ordered at full price.
2. Margin compression on every promo order: commission, food cost and packaging do not shrink with the price, so a 20%
   price cut can be a 50-70% cut in contribution.
3. Cannibalisation of full-price sales in other slots, of other dishes, or on other platforms.

The decision each cycle is which product, platform, time slot, promo type and depth to run, with "no promo" (d = 0)
always on the table. Platform promo tools never offer that option.

## 2. Objective

| Symbol | Meaning |
|---|---|
| P | menu price paid by the customer |
| d | discount depth |
| f | platform commission rate |
| c, g | food cost and packaging per unit |
| q⁰, q | baseline and promo quantity |
| ι | share of the lift that is genuinely new demand |
| κ | contribution lost to cannibalisation |
| F | fixed promo costs |

Contribution per unit at full price and under a restaurant-funded discount (commission on the price paid):

    m⁰ = P(1 − f) − c − g
    m¹(d) = P(1 − d)(1 − f) − c − g

Change in contribution from running the promo:

    ΔΠ = q·m¹ − q⁰·m⁰ − κ − F
       = Δq·m¹  (margin earned on new volume)
       − q⁰·(m⁰ − m¹)  (margin given away on volume you already had)
       − κ − F

A promotion is a trade: a smaller margin on every order you would have received anyway, in exchange for extra orders
at the promo margin. Run it only if ΔΠ > 0.

## 3. Demand model, in layers

0. **Baseline lookup**: average sales by weekday and slot over comparable non-promo weeks.
1. **Log-linear regression** with weekday, slot and promo effects, at category or restaurant level.
2. **Panel regression** with fixed effects (needs 6-12 months).
3. **Hierarchical Bayesian** elasticities that shrink towards the category.
4. **Causal designs**: matched periods, difference-in-differences, and above all pre-committed on/off experiments.
5. **Contextual bandits**, only once many restaurants run promos continuously.

With three months of data from one restaurant, levels 0-1 and one designed experiment are realistic. Promo Profit Lab
implements level 1 at restaurant level (`uplift.py`) and the experiment design (`experiments.py`).

## 4. Impact metrics

Observed promo sales = orders that would have happened anyway + truly incremental orders − orders displaced from
elsewhere. The verdict number is incremental contribution, `Δq·m¹ − q⁰·(m⁰ − m¹) − κ − F`, and the one-line test for an
owner is: *your margin per order dropped from m⁰ to m¹, so you needed U\* more orders; you got X; the promo made or lost
you €Y.*

## 5. Break-even

Total contribution is unchanged when q·m¹ = q⁰·m⁰, so the required uplift is

    U* = m⁰ / m¹ − 1

Worked example: a €10 dish, 30% commission, €2.50 food, €0.50 packaging. At full price m⁰ = €4.00. At −20%,
m¹ = €2.60 and U\* = 54%. At −30%, m¹ = €1.90 and U\* = 111%.

- Low-margin products have explosive break-evens; if m¹ ≤ 0 no volume can ever pay for the promo.
- If only a share ι of the lift is new demand, the observed lift must reach U\*/ι. With ι = 0.6 the −20% example needs
  +90%, not +54%.

## 6. Promo types

| Type | Economics | Use when | Avoid when |
|---|---|---|---|
| % discount | Linear price cut, convex margin cut | Weak slots, high-margin dishes, short tests | Storewide, best sellers at peak, permanent |
| 2x1 | Customer pays P, you pay 2(c + g) | Very high-margin items, perishable stock | Costly proteins and premium dishes |
| Bundle | Discount on a basket with high-margin add-ons | Low attach rate, add-ons at 70-90% margin | Bundling two low-margin mains |
| Free delivery | Fixed € per order, product margin intact | High basket values | Low-AOV restaurants |
| Slot-fenced discount | % discount limited to idle hours | Almost always the right first test | Customers shift from full-price slots |
| Add-on promo | Discount on a cheap add-on with a full-price main | Raising attach rate | Rarely harmful, modest lift |

Fenced promos spend margin surgically; unfenced deep promos need proven uplift before scaling.

## 7. Constraints

Minimum margin floor per dish, maximum discount, kitchen capacity per slot, a never-discount list, platform rules,
stock and perishability, a monthly promo budget, and frequency caps to protect reference prices.

## 8. Decision tree

0. **Eligibility**: reject dishes on the never-discount list, slots near capacity, promos below the margin floor or over
   budget.
1. **Break-even realism**: compute U\*/ι; reject if no evidence makes it plausible.
2. **Context**: discount only in weak slots; in strong slots allow only margin-safe formats (bundles, add-ons).
3. **Guardrails per type**: 2x1 only if P(1 − f) − 2(c + g) clears the floor; start % discounts shallow.
4. **Rank and schedule**: by expected ΔΠ under conservative uplift, at most one or two promos at a time, with a
   pre-committed measurement window and kill criterion.

## 9. Validation plan (four weeks, one pilot restaurant)

1. Descriptive baseline: orders, revenue and AOV by product, weekday and slot.
2. Margins and retrospective audit of every past promo against matched periods.
3. One designed experiment, typically a fenced discount, run on/off on a pre-committed schedule.
4. Impact measurement and a one-page verdict in euros, plus the next test.

## 10-11. MVP and roadmap

The first product was a spreadsheet plus a cleaning notebook. The roadmap runs from descriptive analytics and margin
simulation, through rule-based recommendations and regression-based impact estimation, to systematic experimentation and
only much later automated optimisation across many restaurants.

## 12. Report design

Every number in euros, every formula as a sentence ("you needed +54% orders, you got +31%, the promo cost you about
€180"), and a limitations box that is always present.

## 13. Limitations

Observational uplift is never proof (promos are launched when demand is weak or strong); small samples give wide
intervals and some tests will be inconclusive; wrong food costs propagate into every margin; part of any uplift is
platform placement, not price; competitor promos, weather and events add noise; commission terms under promos vary by
contract; platforms own customer-level data.

## 14. Positioning

A margin-protection and experimentation tool, not a profit-maximisation oracle. The early value is stopping
money-losing promotions and running one clean test a month.

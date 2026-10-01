# Match Feature Catalog (Phase 6)

## Version Specification
- **Feature Set Version**: `match_prediction_v1`
- **Calculation Version**: `temporal_pre_match_v1`
- **Cutoff Guarantee**: $t_{\text{cutoff}} = \min(\text{kickoff}, \text{as\_of})$

---

## 1. Team Strength Features (Elo)
| Feature Name | Type | Range | Description |
|---|---|---|---|
| `home_elo` | float | [1100.0, 2100.0] | Home club rating frozen at kickoff (baseline 1500.0). |
| `away_elo` | float | [1100.0, 2100.0] | Away club rating frozen at kickoff (baseline 1500.0). |
| `elo_diff` | float | [-600.0, +600.0] | Effective rating gap: $(R_H + \Delta H) - R_A$ including +65 home advantage. |

---

## 2. Rolling Form & Momentum Features
| Feature Name | Type | Range | Description |
|---|---|---|---|
| `home_points_l5` | float | [0.0, 3.0] | Home team points per match across last 5 completed fixtures. |
| `away_points_l5` | float | [0.0, 3.0] | Away team points per match across last 5 completed fixtures. |
| `points_diff_l5` | float | [-3.0, +3.0] | Differential in recent points rate: $\text{points}_{H, L5} - \text{points}_{A, L5}$. |
| `home_points_l3` | float | [0.0, 3.0] | Home team points per match across last 3 completed fixtures. |
| `away_points_l3` | float | [0.0, 3.0] | Away team points per match across last 3 completed fixtures. |
| `home_goals_scored_l5` | float | [0.0, 5.0] | Goals scored per match by home team over last 5 fixtures. |
| `away_goals_scored_l5` | float | [0.0, 5.0] | Goals scored per match by away team over last 5 fixtures. |
| `home_goals_conceded_l5` | float | [0.0, 5.0] | Goals conceded per match by home team over last 5 fixtures. |
| `away_goals_conceded_l5` | float | [0.0, 5.0] | Goals conceded per match by away team over last 5 fixtures. |
| `home_goal_diff_l5` | float | [-4.0, +4.0] | Average net goal difference per match in last 5 fixtures. |
| `away_goal_diff_l5` | float | [-4.0, +4.0] | Average net goal difference per match in last 5 fixtures. |
| `home_win_rate_l5` | float | [0.0, 1.0] | Proportion of victories in last 5 fixtures. |
| `away_win_rate_l5` | float | [0.0, 1.0] | Proportion of victories in last 5 fixtures. |

---

## 3. Venue Performance Features
| Feature Name | Type | Range | Description |
|---|---|---|---|
| `home_venue_points_l5` | float | [0.0, 3.0] | Points rate for host club when playing exclusively at home. |
| `away_venue_points_l5` | float | [0.0, 3.0] | Points rate for visiting club when playing exclusively away. |
| `home_venue_goal_diff_l5` | float | [-4.0, +4.0] | Net goal difference for host club in last 5 home games. |
| `away_venue_goal_diff_l5` | float | [-4.0, +4.0] | Net goal difference for visitor in last 5 away games. |

---

## 4. Attack vs Defense Parameters
| Feature Name | Type | Range | Description |
|---|---|---|---|
| `home_attack_strength` | float | [0.40, 2.50] | Relative offensive scoring rate vs 1.30 baseline per team. |
| `home_defense_strength` | float | [0.40, 2.50] | Relative defensive concession rate vs 1.30 baseline per team. |
| `away_attack_strength` | float | [0.40, 2.50] | Visitor offensive scoring rate vs 1.30 baseline. |
| `away_defense_strength` | float | [0.40, 2.50] | Visitor defensive concession rate vs 1.30 baseline. |

---

## 5. Fatigue, Rest & Schedule Features
| Feature Name | Type | Range | Description |
|---|---|---|---|
| `home_rest_days` | float | [0.0, 30.0] | Elapsed days since home team's preceding match. |
| `away_rest_days` | float | [0.0, 30.0] | Elapsed days since away team's preceding match. |
| `rest_days_diff` | float | [-20.0, +20.0] | Rest disparity: $\text{days}_H - \text{days}_A$ (positive favors home). |

---

## 6. Head-to-Head (H2H) Historical Features
| Feature Name | Type | Range | Description |
|---|---|---|---|
| `h2h_matches_count` | int | $\ge 0$ | Total recorded prior encounters between the clubs. |
| `h2h_home_wins` | int | $\ge 0$ | Matches won by the designated host club in H2H history. |
| `h2h_away_wins` | int | $\ge 0$ | Matches won by the designated visiting club in H2H history. |
| `h2h_draws` | int | $\ge 0$ | Drawn fixtures in direct H2H history. |

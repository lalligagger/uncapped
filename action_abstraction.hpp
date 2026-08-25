#ifndef __PURE_CFR_ACTION_ABSTRACTION_HPP__
#define __PURE_CFR_ACTION_ABSTRACTION_HPP__

/* action_abstraction.hpp
 * Richard Gibson, Jun 28, 2013
 *
 * Home of the action_abstraction abstract class and all implementing classes
 *
 * Copyright (C) 2013 by Richard Gibson
 */

/* C / C++ / STL indluces */

/* project_acpc_server includes */
extern "C" {
#include "acpc_server_code/game.h"
}

/* Pure CFR includes */
#include "constants.hpp"

/* Base Class */
class ActionAbstraction {
public:

  ActionAbstraction( );
  virtual ~ActionAbstraction( );

  virtual int get_actions( const Game *game,
			   const State &state,
			   Action actions[ MAX_ABSTRACT_ACTIONS ] ) const = 0;

protected:
};

/* The null action abstraction makes every action in the real game allowable in
 * the abstract game.  Standard for limit games, but not feasible for large
 * nolimit games.
 */
class NullActionAbstraction : public ActionAbstraction {
public:

  NullActionAbstraction( );
  virtual ~NullActionAbstraction( );

  virtual int get_actions( const Game *game,
			   const State &state,
			   Action actions[ MAX_ABSTRACT_ACTIONS ] ) const;

protected:
};

/* The FCPA action abstraction only allows the fold, call, pot (if legal), and
 * allin actions.  Not applicable in limit games, but a good starting point for
 * nolimit games.
 */
class FcpaActionAbstraction : public ActionAbstraction {
public:

  FcpaActionAbstraction( );
  virtual ~FcpaActionAbstraction( );

  virtual int get_actions( const Game *game,
			   const State &state,
			   Action actions[ MAX_ABSTRACT_ACTIONS ] ) const;

protected:
};

/* A compact limit-game abstraction that caps the number of raises on the preflop
 * and flop to 3 total bets, and forces checkdown on the turn and river.  This is
 * a low-memory compromise intended to keep the action tree manageable while
 * keeping the reduced flop abstraction active. */
class Trunc3ActionAbstraction : public ActionAbstraction {
public:

  Trunc3ActionAbstraction( );
  virtual ~Trunc3ActionAbstraction( );

  virtual int get_actions( const Game *game,
			   const State &state,
			   Action actions[ MAX_ABSTRACT_ACTIONS ] ) const;

protected:
};

/* Minimal no-limp variant: only removes the call action at the very first
 * preflop decision point; all other rounds keep the standard legal action set.
 */
class NoLimpActionAbstraction : public ActionAbstraction {
public:

  NoLimpActionAbstraction( );
  virtual ~NoLimpActionAbstraction( );

  virtual int get_actions( const Game *game,
				 const State &state,
				 Action actions[ MAX_ABSTRACT_ACTIONS ] ) const;

protected:
};

/* Same as TRUNC3, but the first preflop action node excludes the call action.
 * This matches the historical no-limp variant used for preflop opening checks.
 */
class Trunc3NoLimpActionAbstraction : public ActionAbstraction {
public:

  Trunc3NoLimpActionAbstraction( );
  virtual ~Trunc3NoLimpActionAbstraction( );

  virtual int get_actions( const Game *game,
				 const State &state,
				 Action actions[ MAX_ABSTRACT_ACTIONS ] ) const;

protected:
};

/* A TRUNC3-style abstraction that keeps the 3-raise cap on every street,
 * instead of forcing checkdown after the flop.  It still uses the compact
 * three-raise limit, but applies it uniformly across all rounds.
 */
class Trunc3x5ActionAbstraction : public ActionAbstraction {
public:

  Trunc3x5ActionAbstraction( );
  virtual ~Trunc3x5ActionAbstraction( );

  virtual int get_actions( const Game *game,
				 const State &state,
				 Action actions[ MAX_ABSTRACT_ACTIONS ] ) const;

protected:
};

#endif


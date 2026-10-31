// Simple transparent research aid, not calibrated, backtested, or a guaranteed forecast.
// The inputs should be sourced from real, recent venue-specific matches, and verified independently.
(function (root) {
  'use strict';
  function number(v) {
    if (v === '' || v === null || v === undefined) return null;
    const n=Number(v); return Number.isFinite(n) && n>=0 && n<=40 ? n : null;
  }
  function overPoisson(mean, threshold) {
    if (number(mean) === null || !Number.isFinite(Number(threshold)) || Number(threshold)<0) return null;
    const target=Math.floor(Number(threshold))+1;
    let p=Math.exp(-mean), sum=p;
    for(let i=1;i<target;i++){p=p*mean/i;sum+=p;}
    return Math.max(0,Math.min(1,1-sum));
  }
  // Neutral arithmetic blend of venue-specific recent attacking and defensive rates.
  // Expected total: (home-for + away-allowed)/2 + (away-for + home-allowed)/2.
  function calculate(inputs) {
    const a=number(inputs.homeFor), b=number(inputs.awayAllowed);
    const c=number(inputs.awayFor), d=number(inputs.homeAllowed);
    if ([a,b,c,d].some(v=>v===null)) return null;
    const mean=(a+b+c+d)/2;
    const line=Number(inputs.line);
    return { mean, probability:overPoisson(mean,line), line };
  }
  root.GoalGridModel={number,overPoisson,calculate};
})(typeof window !== 'undefined' ? window : globalThis);

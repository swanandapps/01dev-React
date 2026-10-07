export interface Subchapter {
  name: string;
  src: string;
}

export interface Chapter {
  name: string;
  subchapters: Subchapter[];
}

export interface Module {
  id?: number;
  title: string;
  description: string;
  src?: string;
}

export interface Track {
  id: number;
  title: string;
  priceINR: string;
  priceELSE: string;
  description: string;
  trailer: string;
  image: string;
  theme: string;
  theme2: string;
  border: string;
  launched: boolean;
  courseContent: Chapter[];
  modules: Module[];
  learnings: string[];
  /** Real student feedback for this course, shown on its page (omit when there is none). */
  testimonials?: { quote: string; name: string; source?: string }[];
}

const tracks: Track[] = [
  {
    id: 1,
    title: "Build a Programming Language",
    priceINR: "179900",
    priceELSE: "2500",
    description: "Every language you use — C++, Java, Python, JavaScript — started as a grammar on someone's whiteboard. In 'Build a Programming Language' you'll design Ember, a small language of your own, and build its tokenizer, parser and tree-walking interpreter from scratch in JavaScript. Along the way you'll learn what separates syntax from semantics, how compilers, interpreters and transpilers really differ, and how an abstract syntax tree turns source text into a running program.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2Ftrail.mp4?alt=media&token=b7256e18-ce75-4272-ad6b-103770c02645",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    theme: "text-green-500",
    theme2: "bg-green-700 hover:bg-green-500",
    border: "border-green-500",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - Introduction", subchapters: [
        { name: "1.1 - What We Will Build: Ember, a Language of Our Own", src: "" },
        { name: "1.2 - Language History: From Machine Code to JavaScript", src: "" },
      ]},
      { name: "Chapter 2 - Human Languages vs Programming Languages", subchapters: [
        { name: "2.1 - What Human Languages Teach Us About Grammar", src: "" },
        { name: "2.2 - Syntax vs Semantics: Is a Language Just Its Syntax?", src: "" },
      ]},
      { name: "Chapter 3 - Language Components", subchapters: [
        { name: "3.1 - Values, Datatypes and Expressions", src: "" },
        { name: "3.2 - Variables, Scope and Control Flow", src: "" },
      ]},
      { name: "Chapter 4 - Language Processors", subchapters: [
        { name: "4.1 - Machine Code, Bytecode and Your Code", src: "" },
        { name: "4.2 - Compilers vs Interpreters vs Transpilers", src: "" },
        { name: "4.3 - AOT vs JIT: How C++, Java, Python and V8 Run Your Code", src: "" },
      ]},
      { name: "Chapter 5 - Designing Ember's Grammar", subchapters: [
        { name: "5.1 - Writing Ember's Grammar in BNF", src: "" },
        { name: "5.2 - Encoding Precedence and Associativity", src: "" },
      ]},
      { name: "Chapter 6 - Lexical Analysis", subchapters: [
        { name: "6.1 - Tokens, Lexemes and Token Types", src: "" },
        { name: "6.2 - Writing the Tokenizer Loop", src: "" },
      ]},
      { name: "Chapter 7 - Building the Abstract Syntax Tree", subchapters: [
        { name: "7.1 - Recursive Descent: Turning Tokens into a Tree", src: "" },
        { name: "7.2 - Parsing Statements, Blocks and Functions", src: "" },
      ]},
      { name: "Chapter 8 - Interpreting the AST", subchapters: [
        { name: "8.1 - Writing a Tree-Walking Evaluator", src: "" },
        { name: "8.2 - Environments: Scoping, Hoisting and Closures", src: "" },
        { name: "8.3 - Running Conditionals, Loops and Function Calls", src: "" },
      ]},
      { name: "Chapter 9 - Finale", subchapters: [
        { name: "9.1 - Running a Real Program in Ember", src: "" },
        { name: "9.2 - Where from Here?", src: "" },
      ]},
    ],
    modules: [
      { id: 1, title: "First Principles: Human Language", description: "Trace the road from machine code to JavaScript, then borrow from human grammar to pin down what syntax and semantics really mean." },
      { id: 2, title: "Language Components", description: "Break any language into values, datatypes, expressions, variables, scope and control flow — the parts Ember will need." },
      { id: 3, title: "Machine Code, Bytecode, Your Code", description: "Follow source down to bytecode and machine code, and see how compilers, interpreters, transpilers and V8's JIT each get it there." },
      { id: 4, title: "Design a Language Grammar", description: "Write Ember's grammar in BNF, with operator precedence and associativity baked into the rules." },
      { id: 5, title: "Lexical Analysis", description: "Turn raw Ember source into a stream of typed tokens with a hand-written tokenizer loop." },
      { id: 6, title: "Build an Abstract Syntax Tree", description: "Write a recursive-descent parser that turns tokens into a tree of expressions, statements, blocks and functions." },
      { id: 7, title: "Interpret a Language AST", description: "Walk the tree to run Ember programs — environments, scoping, hoisting, closures, conditionals and loops included." },
    ],
    learnings: [
      "How C++, Java, Python and JavaScript work",
      "AOT vs JIT Compilation",
      "The importance of Bytecode",
      "How to Design a Language Grammar",
      "The V8 engine",
      "Tokenization of Sourcecode",
      "Parsing Sourcecode to Create Abstract Syntax Tree",
      "Difference between Compiler, Interpreter & Transpiler",
      "How Interpreter works and create one",
      "How languages implement variable scoping",
      "Environments: where a language keeps its variables",
      "Implementing Hoisting",
      "Creation of Datatypes for a Language",
      "Loops, Conditionals support",
    ],
  },
  {
    id: 2,
    title: "Build a Custom Library",
    priceINR: "179900",
    priceELSE: "2500",
    theme: "text-red-500",
    theme2: "bg-red-700 hover:bg-red-500",
    border: "border-red-500",
    description: `Peek under the hood of standard JS libraries and you'll find a world of potential waiting in 'Build a Custom JS Library'. It's not just about bending existing tools to your will; it's about building them from scratch. You'll dive deep into the mechanics of JavaScript, understanding the core principles that make frameworks tick. We're talking closures, callbacks, and prototypes that become your everyday tools for innovation.`,
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2FBCL%20Trailer%20.mp4?alt=media&token=ec2dfe29-e0d1-4050-bb49-83df014c994f",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    launched: true,
    courseContent: [
      { name: "Chapter 1 - Introduction", subchapters: [
        { name: "1.1 - What is this course", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWF1YVlNDSEZAVSMHBwFWRlgAAExBUQcNCgFARl8lGgYGGwxdBANVTAQPBlgZCgIcElIcBhgMHVxLAQJBBxJWUVhHFVgLXl1EBxJIAUdWQUIETRZNUA0XUURVQQE=" },
        { name: "1.2 - What will we build", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWF1bVlNDSEZAVSMHBwFWRlgeGgUfREFVFBdARl8kABoYDEceGUdeEgkXTwgRCw8UVQAHAhYHTlcVVwFGXEEOS0cVQlBERwtLVl4HVUJUWVsHQRAVXVBGXBBUFw==" },
        { name: "1.3 - Mental Models We Will Be Using", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWF1aVlNDSEZAVTkKCAESGE1bQyQcBRYJEFdXRDgDUEFEPwAfBVZTQycGV1dEOhUcHRNGBANdTAAfEV4fABAGB1MHGwMMHVQWVEVdVEtdRkIDQ0RCRV1BCBdMElcGQkhMWl9DEUcKUEVZFVg=" },
      ]},
      { name: "Chapter 2 - Libraries: First Principles", subchapters: [
        { name: "2.1 - What are Libraries and their Types", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuW11YVlNDSEZAVSMHBwFWRlgIAQxWU0MJChAXFR0PEABaBRlHVhINB1gOFwEdDkABHB8NB05dQFZLV1IRA1lbU0RBWVwPSg1eWEBQB19dRF5TFxJMWVFHUBE=" },
      ]},
      { name: "Chapter 3 - Welcome Prototype", subchapters: [
        { name: "3.1 - The Js v1.0", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWl1YVlNDSEZAVSAHA1BBRCIaVltDUF1VTR8VQFAHGQdJBQwXABJHBwoIFwtJXwNHQxEJWERERwcXVk5GV0RfSxRCTF1EQlhHAkoHAEADTVlW" },
        { name: "3.2 - Nature Inherites So Does Javascript", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWl1bVlNDQFFCSFFdVjsSAB0bFkxBUToLCxcXHRsDBlZGWBocTEFRFwoGAUBGXywGXRkYXUwIHxVOCAYWDBVJEhoYEQZUQAtDBRBUWkZIEV5QFF5AWghDRBEHQAZOFwcXWlZMQ0JYXRdb" },
        { name: "3.3 - Meditate on Javascript", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWl1aVlNDSEZAVTkKAhwHFRwMVltDDh1AUUIvB0ELBUdLCQUHVB4EFwwCVBEbBAMbTkxaCkcPSlURSFUWBxBCUhEQEEVQFlBHTEZVAUNcEl9QQEoRWg==" },
        { name: "3.4 - What is this Prototype", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWl1dVlNDSEZAVSMHBwFWRlgAAExBUQcNCgFARl8WBxwABx0KGRZPHhVXTQQYG1sYFhABCFUdHAoWC14UU0RfUE1LF0VQEFEVTEcBVxZIFl1fR15ECVhFXkBRQVNbRAA=" },
        { name: "3.5 - Prototype Enables Inheritance", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWl1cVlNDSEZAVSQdCQEcABEZFkxBUTYLAhAJERxDR0M9BgEWGxoVFgsAF0sZH1JKEhgcVB4MFwgSQxcdDhEBW0xAF1xZRA1LTENQUUtIQAsCRF4VXw9BREAARFdWQQRHX1dNRA==" },
        { name: "3.6 - Hacking Javascript's Prototype", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWl1fVlNDSEZAVTwOBR4aGg9MQVk5ElZXUyIXGxsJAQoEDUceGUdeEgkXTwgRCw8UVQAHAhYHTlMWVwcWUkddSxRBQA5ER1xCVV5cUxdTWVdXQEtBWVhKWEdYEQ==" },
      ]},
      { name: "Chapter 4 - Adding Methods to Our Library", subchapters: [
        { name: "4.1 - Creating Methods", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXV1YVlNDSEZAVTcdAxQHHQYOVltDLBYRCx0BB0ELBUdLCQUHVB4EFwwCVBEbBAMbTkBRCxcIRVNESAUTBkRCUkcSTEULF10XTEBQBRdTElsAEUFHXw==" },
        { name: "4.2 - What are Regular Expressions?", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXV1bVlNDSEZAVSMHBwFWRlgoAQxWU0M3BhUQGA4UUEFELREDGxYSAAwMHBYHQQsFR0sJBQdUHgQXDAJUERsEAxtOEQ5dQl9HUhFIABNdR0JSF0tARVEVWUdMEVNXSlVEWlcQQkRd" },
        { name: "4.3 - Methods Using Regular Expressions", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXV1aXkRBVS4XERwAAgZWRlg8AAAdBlZXUyAAEwoeWx4EXFYSBQdcHgAHGwRSGwkeFhpVW0RcR1VLB1JfVBJdXlhHQFpbXggQAkRIVxBcFlpWR0MXXFoR" },
        { name: "4.4 - Organising The Library", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXV1dVlNDSEZAVTsdARQdHRsAHQ5WU0MxCxdARl8qHBEGCRsKRx4RR1oCHhFJAgMRGhVOHRwCFg9OAAYQBBVcXhFeQQ1bFURHURJQTktSQVZLEBdFCwpDCkICFldR" },
        { name: "4.5 - Testing The Library", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXV1cVlNDSEZAVSEcDxsUUVpZPBwBREFVLxsHBg4UDFZGWAYdTEFRMhUTXAgEW1kUHwBVBBYNGgBVEQwZABpSVEURQFAIRQheVxADUl9RF1dRWEpCDF1eCEUHRVFSRFESXVAQ" },
      ]},
      { name: "Chapter 5 - Goodbye Prototype", subchapters: [
        { name: "5.1 - Prototype, a Hero Turned Villain", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXF1YVlNDSEZAVSQdCQEcABEZFkxBIlZXUzNARl8uEAEbTVtDPQYTHQAHV1dEOQ8ZHxUBB10EA1VMBA8GWBkKAhwSUhwGGAwdXENWUkVdQFwFWEUQDA1eXUBYS0gBQlZGQl5ESxJbWEJQQVJFUw==" },
        { name: "5.2 - When to Use Prototype and When To Not", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXF1bVlNDSEZAVSMHAxtWRlg9HExBUSYWBldXRA4IEVZGWD4bDB1EQVU3HUBGXygaB1oFGUdWEg0HWA4XAR0OQAEcHw0HTloSURZRB0VWWV5URBdZXApCXF4AQgRbX1xGCwJNFkZQUUIKSw==" },
        { name: "5.3 - Summary So Far", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXF1aVlNDSEZAVScaCxgSBhFHHhlHXhIJF08IEQsPFFUABwIWB04DRlNQQlYQV0tCF0wKREdfQAVeXVdEAFlcX0BDFlBdFwoXV0c=" },
      ]},
      { name: "Chapter 6 - Welcome Window", subchapters: [
        { name: "6.1 - What is Window", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuX11YVlNDSEZAVSMHBwFWRlgAAExBUSQMDRYKA0ELBUdLCQUHVB4EFwwCVBEbBAMbTkVYDBJbQlFBSFARVURCUhNKQ0VREl8XTBdSB0pcR1ZeE0UQXA==" },
        { name: "6.2 - Register Library to Window", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuX11bVlNDSEZAVSYKARwAAA0bVltDLRoHERMXDUpURQcbTVtDPhoPFwoUXAgEW1kUHwBVBBYNGgBVEQwZABpSABNBQg5eSlBeV0EGUF9REVcHWBISXQteWRJYRFZRF1YRW1NA" },
        { name: "6.5 - IIFE, To The Rescue", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuX11cVlNDSEZAVSAHA1BBRCEgNSxdDANRXBMJAFILEBcdCU8HBhgEHVhaQ11DVlBNEllbURYKXlUWVQdfXRVdUFhETQpbQlBEUxJXAUA=" },
      ]},
      { name: "Chapter 7 - Making Library Backend Compatible", subchapters: [
        { name: "7.1 - Registering Library to Global Object", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXl1YVlNDSEZAVSYKARwAAA0bGgcUREFVLxsHBg4UDFZGWB0cTEFRNAkMEAQYSlRFPBYCDBAdXQwDUVwTCQBSCxAXHQlPBwYYBB1YBkpcR1dWQRFZDQpECF5VSwNSXwcWXVBYFhIMCkELFQJHUgBB" },
        { name: "7.2 - Root, To The Rescue", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuXl1bVlNDSEZAVT0CFhkWGQ0HBwAdBlZXUyAKGxtIGANAVwgfHU4MFgEKE0MAAA0QHUlZXUQPEAdABk4TBxdeS0FFEVpESgxDUV5XWkMHQFtXFxFGWFo=" },
      ]},
      { name: "Chapter 8 - How to Develop NPM Package", subchapters: [
        { name: "8.1 - The `npm link` command", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuUV1YVlNDSEZAVSAHA1BBRE1fQwcDDFZXUx4MGgRDQ0NRWlkQBh4MEgsHXAgEW1kUHwBVBBYNGgBVEQwZABpSBU1ARQsMEVBeVUEHW19RRAlTWBFAUQ1eWxcHQV0BRAYQXAVH" },
        { name: "8.2 - Testing Our NPM Package", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuUV1bVlNDSEZAVSEcDxsUUVpZHBwBREFVLx0GFQNDR0M6OCRWW0MREgYIEwIRQQsFR0sJBQdUHgQXDAJUERsEAxtOFglQRAxABUVIUxFVRUJSQhVGRQgVUENMQlxWRFBHXVAXQRJZ" },
      ]},
      { name: "Chapter 9 - Welcome ES Modules", subchapters: [
        { name: "9.1 - Window is good but ...", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuUF1YVlNDSEZAVSMGCBEcA01bQyQWFRsKB1dXRAYVUEFEDwYcDVZTQwcWBkBGX0hbXVoFGUdWEg0HWA4XAR0OQAEcHw0HTllAVEtUUEEGWVheQUVZXF9AC14DS1dbX1FHX1AWQENaWxYMEQ==" },
      ]},
      { name: "Chapter 10 - ES Modules", subchapters: [
        { name: "10.1 - What Are ES Modules", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWENHQkRBVU5XV0Q4DhQHUVpZEhsWREFVJiFARl8rGhcBBAwARx4RR1oCHhFJAgMRGhVOHRwCFg9OBgAQUBVeBUxeElBZQ0RHVBFQThAEQltLQENFDVFAD0FUFldW" },
        { name: "10.2 - Creating ESM Based Library", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWENHQURBVU5XV0QsFBASAAEHFExBUTY2LldXRA0HBhYQTVtDJRoDAQQRC0sZH1JKEhgcVB4MFwgSQxcdDhEBW0xLF1hZFQwRTBdVABdIQFZWQ15MWFhHRBICRFFVEVAQCV5HFg==" },
        { name: "10.3 - Testing Library on Backend", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWENHQERBVU5XV0Q7AwYHHQYOVltDLRoHERMXDUpURRwaTVtDKxICGAANFksZH1JKEhgcVB4MFwgSQxcdDhEBW0ZEQ1gLQVtDTERVV0VIQFsCTV5NWQxGREoAFlMCFwAQVldGEQ==" },
      ]},
      { name: "Chapter 11 - Publishing Our Library as NPM Package", subchapters: [
        { name: "11.1 - Publishing using `np`", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWEJHQkRBVU5XV0Q/ExcfHRsBGgcUREFVFgEMGghDR0NRXlkdGVZXQ0sOAlFLDgoBThkNDRoIVRUcDgYcWEwNBUBGFl8PXltGWUBIV0JWREIER0MXRV5AUUoAFlxWEVYQDg==" },
        { name: "11.2 - More methods and Testing Library on Frontend Application", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWEJHQURBVU5XV0QiCQcWUVpZHgwHCRwBEFdXRA4IEVZGWD0WGgcIHQJGQFU4BgQHEgYRTEFZHA9WV1M0FxsBEhAdEE1bQygDER8MABMRHQAIWx4EXFYSBQdcHgAHGwRSGwkeFhpVW0QMR1IVBlRfU0ILX1hHQwpcXghEBEBIUhQARF9WE0oXWAtB" },
      ]},
      { name: "Chapter 12 - Finale", subchapters: [
        { name: "12.1 - How Axios Library Uses 3 Methods We Learned", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWEFHQkRBVU5XV0QnCQJWRlgoCwAcElZXUz4MFh0HBwpRWlkmGhYSVldTQUBGXysQBxwHDQBMQVEkAEZAVTgKBwcdEQxHHhlHXhIJF08IEQsPFFUABwIWB05YSgBRFlARXUsTFU1YREdYElleXQUWAFlfBURCF1kKQ18VWEA=" },
        { name: "12.2 - Complete Course Summary", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWEFHQURBVU5XV0QsCRgDGA0dFkxBUTAKFgAWEUpURSABBQQSGwpPHhVXTQQYG1sYFhABCFUdHAoWC15EUENfVkFBEUVcFl1DTEcDVkZIFlkARV4QX1gXDUBRQwBQQ1w=" },
        { name: "12.3 - Where from Here?", src: "HBwdAxpJTlwDCgAAFg4VEAAABxsSDhZPFAoMFQkRDhYcAFoLBh5GBVFcB0wGCgQLAwNeTVtcQFldAAMVEAIKAEEFGh5bB0YwHAAVHAgvGwcGDhQMVkYuWEFHQERBVU5XV0Q4DhABEU1bQw8BDh5AUUINER0DUEAyRgQDXUwAHxFeHwAQBgdTBxsDDB1UQldKAQVEURdCU0JAEkVdElxDTEsGVEdIRgxVTBFMXloVUEVX" },
      ]},
    ],
    modules: [
      { id: 1, title: "Library: First Principles", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Highlights%2FBCL%2F1.mp4?alt=media&token=b36f5b4e-84bd-4545-9bd3-b5fec960a10a", description: "Start your Open Source Journey by building a library for People. Discover the art of crafting a library in Js 1.0 to Js 10.0." },
      { id: 2, title: "Architecture: The Js 1.0", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Highlights%2FBCL%2F2.mp4?alt=media&token=31d0607b-90d2-4d37-b552-7113b14d4d16,", description: "We Study the Books and Blogs written by Brandon Eich himself, The Creator of Javascript." },
      { id: 3, title: "Plugging to Js Prototype", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Highlights%2FBCL%2F3.mp4?alt=media&token=47afa4a0-adb1-46b0-b6f6-c68aee0f1159", description: "Inject your genius into JS's prototype. It's where your methods become part of something bigger." },
      { id: 4, title: "Library Design", description: "Start from simple functions like mask, shorten, highlight using regular expressions to create more advanced functions." },
      { id: 5, title: "Window Pollution, Once and for all!", description: "Navigate the tricky waters of window pollution. Clean code, clean conscience." },
      { id: 6, title: "NPM Package Development", description: "You know `npm init`, You know `npm install` but do you know `npm link`?" },
      { id: 7, title: "ES Modules, New kid on the block", description: "Meet ES Modules, the cool new kid in town for JavaScript modules." },
    ],
    learnings: [
      "The Iniital Architectecture of Javascript",
      "Type OF Libraries: Utility vs Wrapper vs Framework",
      "How to use [[PROTOTYPE]] to create Library",
      "What Causes Prototype Polution",
      "How Lodash, Axios are added to Window",
      "Problem of Window Pollution and How to Avoid",
      "Module Resolution Algorithm of Node Js",
      "Module Pattern using IIFE for Encapsulation",
      "Window vs Global and The ROOT Variable",
      "`npm link` command for local npm package development",
      "ES6 file level scoping",
      "Npm package publishing using `np` package",
    ],
    testimonials: [
      { quote: "Thanks to the incredible team at the01.dev, I've crafted a powerful data visualization library for my team!",
        name: "Palacharla Narendra", source: "on X" },
    ],
  },
  {
    id: 4,
    priceINR: "179900",
    priceELSE: "2500",
    title: "Product Engineering Essentials",
    theme: "text-orange-500",
    theme2: "bg-orange-700 hover:bg-orange-500",
    border: "border-orange-500",
    description: "The gap between a developer and a product engineer isn't syntax — it's knowing why the language behaves the way it does and how code actually reaches users. 'Product Engineering Essentials' starts with first-principles thinking and reading specs and source, then rebuilds JavaScript's architecture from JS 1.0 through prototypes, the event loop and functional patterns. You'll carry one running project the whole way — a link-preview widget you design from first principles, build with those patterns, then review, profile and ship to production.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F1.3%20-%20Mental%20Models%20We%20Will%20Be%20Using.mp4?alt=media&token=e5687982-e676-42ad-a2e0-8596b3b960f9",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - The Engineer's Mindset", subchapters: [
        { name: "1.1 - Why Most Engineers Stop at the Surface", src: "" },
        { name: "1.2 - First Principles Thinking for Engineers", src: "" },
        { name: "1.3 - Reading Specs and Source Code", src: "" },
      ]},
      { name: "Chapter 2 - JavaScript Architecture", subchapters: [
        { name: "2.1 - The Wave Model of JavaScript", src: "" },
        { name: "2.2 - How JS 1.0 Was Designed", src: "" },
        { name: "2.3 - Why JavaScript Evolved This Way", src: "" },
      ]},
      { name: "Chapter 3 - Prototypes and Inheritance", subchapters: [
        { name: "3.1 - [[PROTOTYPE]] Under the Hood", src: "" },
        { name: "3.2 - The Prototype Chain Visualized", src: "" },
        { name: "3.3 - Hacking Prototype", src: "" },
      ]},
      { name: "Chapter 4 - Asynchronous JavaScript", subchapters: [
        { name: "4.1 - The Event Loop: First Principles", src: "" },
        { name: "4.2 - Callbacks, Promises, and Async/Await Internals", src: "" },
        { name: "4.3 - The Microtask Queue", src: "" },
      ]},
      { name: "Chapter 5 - Functional Programming Patterns", subchapters: [
        { name: "5.1 - Pure Functions and Immutability", src: "" },
        { name: "5.2 - Function Composition", src: "" },
        { name: "5.3 - Closures as State", src: "" },
      ]},
      { name: "Chapter 6 - Production Engineering", subchapters: [
        { name: "6.1 - Code Review Culture", src: "" },
        { name: "6.2 - Performance Profiling", src: "" },
        { name: "6.3 - Ship It: From PR to Production", src: "" },
      ]},
    ],
    modules: [
      { title: "Language Fundamentals Mastery", description: "Think from first principles, read specs and source like a senior engineer, and trace JavaScript from the JS 1.0 design to the [[PROTOTYPE]] chain you can hack yourself." },
      { title: "Async & Functional Patterns", description: "Take the event loop, promises and the microtask queue apart, then structure code with pure functions, composition and closures as state." },
      { title: "Production Engineering", description: "Ship like a product engineer: review code well, profile before you optimise, and take a pull request all the way to production." },
    ],
    learnings: ["Architecture of JavaScript as Waves in water", "The Js 1.0", "Hacking [[PROTOTYPE]]", "The event loop and the microtask queue", "Closures as state and function composition", "Taking a PR from code review to production"],
  },
  {
    id: 5,
    priceINR: "179900",
    priceELSE: "2500",
    title: "Build a State Management Library",
    theme: "text-blue-400",
    theme2: "bg-blue-700 hover:bg-blue-500",
    border: "border-blue-400",
    description: "You use Pinia, Redux, Zustand every day — but do you actually know how they work? In 'Build a State Management Library' we strip it all down and build one from first principles. Reactivity, computed values, actions, middleware, time-travel debugging — all engineered by you, from scratch, in plain JavaScript.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/compress%20shot.mp4?alt=media&token=eda2132e-c47b-4f16-b683-f6cc4dad5277",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - State: First Principles", subchapters: [
        { name: "1.1 - What is State and Why It's Hard", src: "" },
        { name: "1.2 - How Redux, Zustand, Pinia Work Under the Hood", src: "" },
        { name: "1.3 - What We Will Build", src: "" },
      ]},
      { name: "Chapter 2 - JavaScript Proxy", subchapters: [
        { name: "2.1 - Proxy: The Intercept Layer", src: "" },
        { name: "2.2 - The Reflect API", src: "" },
        { name: "2.3 - Building a Reactive Primitive", src: "" },
      ]},
      { name: "Chapter 3 - The Core Store", subchapters: [
        { name: "3.1 - State Container Architecture", src: "" },
        { name: "3.2 - Subscriptions and Listeners", src: "" },
        { name: "3.3 - getState, setState, subscribe", src: "" },
      ]},
      { name: "Chapter 4 - Computed Properties", subchapters: [
        { name: "4.1 - Derived State: The Problem", src: "" },
        { name: "4.2 - Dependency Tracking with WeakMap", src: "" },
        { name: "4.3 - Lazy Memoization", src: "" },
      ]},
      { name: "Chapter 5 - Actions and Async", subchapters: [
        { name: "5.1 - Explicit Mutations", src: "" },
        { name: "5.2 - Async Actions with Optimistic Updates", src: "" },
        { name: "5.3 - Rollback on Failure", src: "" },
      ]},
      { name: "Chapter 6 - Middleware System", subchapters: [
        { name: "6.1 - The Middleware Pattern", src: "" },
        { name: "6.2 - Building a Logger Plugin", src: "" },
        { name: "6.3 - Persistence Plugin (localStorage)", src: "" },
      ]},
      { name: "Chapter 7 - Time-Travel Debugging", subchapters: [
        { name: "7.1 - Snapshot-Based State History", src: "" },
        { name: "7.2 - Undo / Redo Implementation", src: "" },
        { name: "7.3 - How Redux DevTools Works Under the Hood", src: "" },
      ]},
      { name: "Chapter 8 - Finale", subchapters: [
        { name: "8.1 - Comparing Our Library to Zustand", src: "" },
        { name: "8.2 - Publishing as an NPM Package", src: "" },
        { name: "8.3 - Where from Here?", src: "" },
      ]},
    ],
    modules: [
      { title: "Reactive State Fundamentals", description: "Understand what makes state reactive and build the core observer/subscriber engine using JavaScript Proxy." },
      { title: "Computed State & Derived Values", description: "Implement lazy memoized computed properties that recompute only when their dependencies change." },
      { title: "Actions & Mutations", description: "Design explicit mutation patterns and async actions with optimistic updates and rollback support." },
      { title: "Middleware & Plugins", description: "Build a plugin system — implement a logger plugin and a localStorage persistence plugin from scratch." },
      { title: "Time-Travel Debugging", description: "Store state snapshots and implement undo/redo — understand how Redux DevTools works under the hood." },
    ],
    learnings: ["JavaScript Proxy — the engine behind reactivity", "Dependency tracking with WeakMap", "Observer pattern from scratch", "Memoized computed properties", "Undo/redo with state snapshots"],
  },
  {
    id: 6,
    priceINR: "179900",
    priceELSE: "2500",
    title: "Build a Web Framework from Scratch",
    theme: "text-purple-400",
    theme2: "bg-purple-700 hover:bg-purple-500",
    border: "border-purple-400",
    description: "Express, Fastify, Hono — they all started with the same question: how does an HTTP request become a response? In this course you'll answer that question by building a complete web framework from scratch.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/compress%20shot.mp4?alt=media&token=eda2132e-c47b-4f16-b683-f6cc4dad5277",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - HTTP: First Principles", subchapters: [
        { name: "1.1 - What is HTTP and Why It Was Invented", src: "" },
        { name: "1.2 - The HTTP Wire Format", src: "" },
        { name: "1.3 - Headers, Body, and Status Codes", src: "" },
      ]},
      { name: "Chapter 2 - Building the HTTP Server", subchapters: [
        { name: "2.1 - Node.js net.createServer()", src: "" },
        { name: "2.2 - Parsing Raw HTTP Requests", src: "" },
        { name: "2.3 - Sending Raw HTTP Responses", src: "" },
      ]},
      { name: "Chapter 3 - Routing Engine", subchapters: [
        { name: "3.1 - Naive String Matching", src: "" },
        { name: "3.2 - Radix Tree Architecture", src: "" },
        { name: "3.3 - Dynamic :params and Wildcards", src: "" },
      ]},
      { name: "Chapter 4 - Middleware Pipeline", subchapters: [
        { name: "4.1 - What is Middleware", src: "" },
        { name: "4.2 - The next() Pattern", src: "" },
        { name: "4.3 - Error-Handling Middleware", src: "" },
      ]},
      { name: "Chapter 5 - Request & Response Abstractions", subchapters: [
        { name: "5.1 - The req Object", src: "" },
        { name: "5.2 - The res Object", src: "" },
        { name: "5.3 - JSON, HTML, and Binary Responses", src: "" },
      ]},
      { name: "Chapter 6 - Plugins and Extensions", subchapters: [
        { name: "6.1 - Plugin Architecture", src: "" },
        { name: "6.2 - Body Parser from Scratch", src: "" },
        { name: "6.3 - Static File Server", src: "" },
      ]},
      { name: "Chapter 7 - Finale", subchapters: [
        { name: "7.1 - How Fastify Routes 30x Faster than Express", src: "" },
        { name: "7.2 - Comparing Our Framework to Express", src: "" },
        { name: "7.3 - Where from Here?", src: "" },
      ]},
    ],
    modules: [
      { title: "HTTP from Scratch", description: "Understand the HTTP wire format at the TCP level." },
      { title: "Routing Engine", description: "Build a radix-tree based router with static routes, dynamic :param matching, wildcards." },
      { title: "Middleware Pipeline", description: "Implement the middleware chain pattern — understand how next() works." },
    ],
    learnings: ["HTTP wire format — headers, body, framing", "Radix tree routing — how Fastify routes so fast", "The middleware chain and next() implementation"],
  },
  {
    id: 7,
    priceINR: "179900",
    priceELSE: "2500",
    title: "JavaScript Engine Internals",
    theme: "text-sky-400",
    theme2: "bg-sky-700 hover:bg-sky-500",
    border: "border-sky-400",
    description: "Every time you write JavaScript, V8 is making thousands of decisions about your code. JIT compilation, hidden classes, deoptimization, garbage collection — these aren't black-box magic, they're engineering decisions you can understand.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/compress%20shot.mp4?alt=media&token=eda2132e-c47b-4f16-b683-f6cc4dad5277",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - Inside V8: The Big Picture", subchapters: [
        { name: "1.1 - What Happens When You Run JavaScript", src: "" },
        { name: "1.2 - The V8 Pipeline Overview", src: "" },
        { name: "1.3 - Setting Up: --print-bytecode and --trace-opt", src: "" },
      ]},
      { name: "Chapter 2 - Parsing and the AST", subchapters: [
        { name: "2.1 - Tokenization in V8", src: "" },
        { name: "2.2 - The Abstract Syntax Tree", src: "" },
        { name: "2.3 - Lazy Parsing: V8's First Optimization", src: "" },
      ]},
      { name: "Chapter 3 - Ignition: The Bytecode Interpreter", subchapters: [
        { name: "3.1 - What is Bytecode", src: "" },
        { name: "3.2 - Reading V8 Bytecode", src: "" },
        { name: "3.3 - Registers and the Accumulator", src: "" },
      ]},
      { name: "Chapter 4 - TurboFan: JIT Compilation", subchapters: [
        { name: "4.1 - What is JIT Compilation", src: "" },
        { name: "4.2 - Type Feedback and Speculation", src: "" },
        { name: "4.3 - Deoptimization: When JIT Bails Out", src: "" },
      ]},
      { name: "Chapter 5 - Hidden Classes and Shapes", subchapters: [
        { name: "5.1 - How V8 Represents Objects", src: "" },
        { name: "5.2 - Shape Transitions", src: "" },
        { name: "5.3 - Inline Caches (IC)", src: "" },
      ]},
      { name: "Chapter 6 - Garbage Collection", subchapters: [
        { name: "6.1 - The V8 Heap Layout", src: "" },
        { name: "6.2 - Minor GC: Scavenger", src: "" },
        { name: "6.3 - Major GC: Mark-Sweep-Compact", src: "" },
      ]},
      { name: "Chapter 7 - Writing V8-Friendly Code", subchapters: [
        { name: "7.1 - Monomorphic vs Polymorphic Code", src: "" },
        { name: "7.2 - What Triggers Deoptimization", src: "" },
        { name: "7.3 - Profiling with --prof", src: "" },
      ]},
    ],
    modules: [
      { title: "Parsing & The AST", description: "Trace source code through the tokenizer and parser." },
      { title: "Ignition: The Bytecode Interpreter", description: "Read V8 bytecode, understand the register machine." },
      { title: "TurboFan: The JIT Compiler", description: "Understand type feedback, speculative optimization, and deoptimization." },
      { title: "Hidden Classes & Object Shapes", description: "Learn how V8 creates hidden classes for your objects." },
    ],
    learnings: ["V8 pipeline: Parse → Ignition → TurboFan", "Reading bytecode with --print-bytecode", "How JIT compilation and deoptimization work", "Hidden classes and inline caches"],
  },
  {
    id: 8,
    priceINR: "179900",
    priceELSE: "2500",
    title: "Build a Real-Time System",
    theme: "text-pink-400",
    theme2: "bg-pink-700 hover:bg-pink-500",
    border: "border-pink-400",
    description: "WebSockets, pub/sub, presence detection, Redis Streams — real-time systems have a reputation for being hard. In 'Build a Real-Time System' you'll build one from scratch.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/compress%20shot.mp4?alt=media&token=eda2132e-c47b-4f16-b683-f6cc4dad5277",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - Real-Time: First Principles", subchapters: [
        { name: "1.1 - What Makes a System Real-Time", src: "" },
        { name: "1.2 - Polling vs Long-Polling vs WebSockets", src: "" },
        { name: "1.3 - What We Will Build", src: "" },
      ]},
      { name: "Chapter 2 - TCP and the WebSocket Handshake", subchapters: [
        { name: "2.1 - TCP: The Foundation", src: "" },
        { name: "2.2 - The HTTP Upgrade Request", src: "" },
        { name: "2.3 - The WebSocket Frame Format", src: "" },
      ]},
      { name: "Chapter 3 - Building the WebSocket Server", subchapters: [
        { name: "3.1 - Accepting Connections", src: "" },
        { name: "3.2 - The Client Registry", src: "" },
        { name: "3.3 - Broadcasting Messages", src: "" },
      ]},
      { name: "Chapter 4 - Pub/Sub Architecture", subchapters: [
        { name: "4.1 - Rooms and Channels", src: "" },
        { name: "4.2 - Subscribe and Unsubscribe", src: "" },
        { name: "4.3 - Message Fan-Out", src: "" },
      ]},
      { name: "Chapter 5 - Presence and Heartbeats", subchapters: [
        { name: "5.1 - Detecting Disconnections", src: "" },
        { name: "5.2 - Ping/Pong Protocol", src: "" },
        { name: "5.3 - Presence Lists", src: "" },
      ]},
      { name: "Chapter 6 - Redis Integration", subchapters: [
        { name: "6.1 - Why In-Memory Pub/Sub Doesn't Scale", src: "" },
        { name: "6.2 - Redis Pub/Sub", src: "" },
        { name: "6.3 - Redis Streams for Persistent Events", src: "" },
      ]},
      { name: "Chapter 7 - Scaling Horizontally", subchapters: [
        { name: "7.1 - The Sticky Sessions Problem", src: "" },
        { name: "7.2 - Redis as the Message Broker", src: "" },
        { name: "7.3 - Load Balancing WebSocket Connections", src: "" },
      ]},
    ],
    modules: [
      { title: "TCP & The WebSocket Upgrade", description: "Go below the WebSocket API — understand the HTTP Upgrade handshake." },
      { title: "Building the WebSocket Server", description: "Accept connections, maintain a client registry, broadcast messages." },
      { title: "Pub/Sub Architecture", description: "Build in-memory pub/sub with rooms and channels." },
    ],
    learnings: ["WebSocket handshake and wire framing", "Connection registry and heartbeat detection", "Redis Pub/Sub vs Redis Streams", "Scaling WebSockets horizontally"],
  },
  {
    id: 9,
    title: "JavaScript Deep Dive",
    priceINR: "149900",
    priceELSE: "2000",
    description: "Go beneath the syntax and understand how JavaScript actually works — scope and closures, prototype inheritance and classes, the V8 engine and hidden classes, and the event loop that keeps everything responsive. You'll build mini-runtime, a small model of the JavaScript runtime written in JavaScript itself: a call stack, a scope-chain resolver, a prototype lookup and an event-loop simulator, one lecture at a time. This course builds the mental models that separate engineers who use JavaScript from engineers who understand it.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2Ftrail.mp4?alt=media&token=b7256e18-ce75-4272-ad6b-103770c02645",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    theme: "text-yellow-400",
    theme2: "bg-yellow-600 hover:bg-yellow-500",
    border: "border-yellow-500",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - How JavaScript Runs", subchapters: [
        { name: "1.1 - What We Will Build: mini-runtime", src: "" },
        { name: "1.2 - From Source Text to Running Code", src: "" },
        { name: "1.3 - Execution Contexts and the Call Stack", src: "" },
      ]},
      { name: "Chapter 2 - Scope and Closures", subchapters: [
        { name: "2.1 - Lexical Scope and the Scope Chain", src: "" },
        { name: "2.2 - Hoisting and the Temporal Dead Zone", src: "" },
        { name: "2.3 - Closures: Functions That Remember Their Scope", src: "" },
      ]},
      { name: "Chapter 3 - Functions, this and new", subchapters: [
        { name: "3.1 - How this Gets Bound: The Four Rules", src: "" },
        { name: "3.2 - Constructor Functions and the new Keyword", src: "" },
      ]},
      { name: "Chapter 4 - Objects & Inheritance", subchapters: [
        { name: "4.1 - Prototype Inheritance", src: "" },
        { name: "4.2 - Classes Are Sugar Over the Prototype Chain", src: "" },
        { name: "4.3 - Writing Object.create and instanceof by Hand", src: "" },
      ]},
      { name: "Chapter 5 - Inside the Engine", subchapters: [
        { name: "5.1 - V8 Engine and Hidden Classes", src: "" },
        { name: "5.2 - Inline Caches and Monomorphic Code", src: "" },
      ]},
      { name: "Chapter 6 - Concurrency", subchapters: [
        { name: "6.1 - The Event Loop and Microtasks", src: "" },
        { name: "6.2 - Writing an Event Loop Simulator", src: "" },
        { name: "6.3 - async/await Is Just .then Underneath", src: "" },
      ]},
      { name: "Chapter 7 - Finale", subchapters: [
        { name: "7.1 - Tracing One Bug Through Every Layer", src: "" },
        { name: "7.2 - Where from Here?", src: "" },
      ]},
    ],
    modules: [
      { title: "Execution, Scope & Closures", description: "Follow code from source text onto the call stack, then build mini-runtime's scope chain to explain hoisting, the TDZ and closures." },
      { title: "Prototype Inheritance", description: "Bind this, wire up new, and see how objects delegate to their prototype — why it's delegation not copying, and why class is just sugar on top." },
      { title: "V8 Hidden Classes", description: "How V8 gives objects hidden shapes, how inline caches use them to optimize property access, and how to avoid deopts." },
      { title: "The Event Loop", description: "Tasks vs microtasks, an event-loop simulator built by hand, and why a resolved Promise beats setTimeout(0)." },
      { title: "Putting It Together", description: "Trace one real bug through scope, prototypes, the engine and the event loop — every layer of mini-runtime at once." },
    ],
    learnings: ["Execution contexts and the call stack", "Scope chains, hoisting and closures", "The prototype chain and property lookup", "Why class is sugar over prototypes", "Hidden classes and V8 optimization", "Tasks vs microtasks", "Why await is just .then under the hood"],
  },
  {
    id: 10,
    title: "Web APIs and Real-Time",
    priceINR: "149900",
    priceELSE: "2000",
    description: "Learn how the web moves data in real time. You'll build a live match scoreboard and push its updates to the browser four ways — short polling, long-polling, Server-Sent Events and WebSockets — crossing the HTTP/WebSocket boundary at the Upgrade handshake. By the end you'll know when to reach for long-polling versus a full-duplex WebSocket connection, what each one really costs, and how to keep a live connection alive when the network isn't.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2Ftrail.mp4?alt=media&token=b7256e18-ce75-4272-ad6b-103770c02645",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    theme: "text-cyan-400",
    theme2: "bg-cyan-700 hover:bg-cyan-500",
    border: "border-cyan-500",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - HTTP and the Push Problem", subchapters: [
        { name: "1.1 - What We Will Build: A Live Scoreboard", src: "" },
        { name: "1.2 - The Request/Response Contract", src: "" },
        { name: "1.3 - Short Polling the Scoreboard", src: "" },
        { name: "1.4 - Long-Polling: Holding the Request Open", src: "" },
      ]},
      { name: "Chapter 2 - The WebSocket Boundary", subchapters: [
        { name: "2.1 - The Upgrade Header: Asking HTTP to Switch Protocols", src: "" },
        { name: "2.2 - WebSocket Handshake", src: "" },
        { name: "2.3 - Frames, Opcodes and Masking", src: "" },
        { name: "2.4 - The Browser WebSocket API", src: "" },
      ]},
      { name: "Chapter 3 - Choosing a Transport", subchapters: [
        { name: "3.1 - Long-Polling vs WebSockets", src: "" },
        { name: "3.2 - Server-Sent Events: One-Way Push over HTTP", src: "" },
        { name: "3.3 - Measuring the Cost: Bytes, Latency and Open Connections", src: "" },
      ]},
      { name: "Chapter 4 - Keeping Connections Alive", subchapters: [
        { name: "4.1 - Reconnecting with Exponential Backoff", src: "" },
        { name: "4.2 - Heartbeats and Detecting Dead Connections", src: "" },
        { name: "4.3 - Backpressure and bufferedAmount", src: "" },
      ]},
      { name: "Chapter 5 - Finale", subchapters: [
        { name: "5.1 - Shipping the Scoreboard: One Transport per Feature", src: "" },
        { name: "5.2 - Where from Here?", src: "" },
      ]},
    ],
    modules: [
      { title: "HTTP and Polling", description: "See why request/response can't push, then fake it for the scoreboard with short polling and long-polling." },
      { title: "The Upgrade Handshake", description: "How an HTTP request becomes a WebSocket connection, and what travels over the wire once it does." },
      { title: "Long-Polling vs WebSockets", description: "The real cost of each transport, where Server-Sent Events fit between them, and when to use which." },
      { title: "Resilient Connections", description: "Reconnects with backoff, heartbeats and backpressure — what keeps a live UI alive on a bad network." },
    ],
    learnings: ["The HTTP Upgrade handshake", "Full-duplex framing", "Long-polling trade-offs", "Server-Sent Events", "Choosing the right real-time transport", "Reconnects, heartbeats and backpressure"],
  },
  {
    id: 11,
    title: "React Performance Patterns",
    priceINR: "149900",
    priceELSE: "2000",
    description: "Make React fast on purpose. You'll take a deliberately slow trading dashboard — a live 5,000-row price table with filters — profile it, and fix it one measured change at a time. Along the way you'll learn what actually triggers re-renders, how memoization and computed state cut wasted work, and how React.memo, useCallback, and useMemo fit together — including the reference-equality traps that quietly defeat them.",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2Ftrail.mp4?alt=media&token=b7256e18-ce75-4272-ad6b-103770c02645",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    theme: "text-sky-400",
    theme2: "bg-sky-700 hover:bg-sky-500",
    border: "border-sky-500",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - How React Renders", subchapters: [
        { name: "1.1 - What We Will Build: A Dashboard That Lags on Purpose", src: "" },
        { name: "1.2 - Render vs Commit: What React Actually Does", src: "" },
        { name: "1.3 - What Triggers a Re-render", src: "" },
        { name: "1.4 - Shallow Equality: How React Compares Props and State", src: "" },
      ]},
      { name: "Chapter 2 - Measure Before You Fix", subchapters: [
        { name: "2.1 - Profiling the Dashboard with React DevTools", src: "" },
        { name: "2.2 - Reading the Flame Graph for Wasted Renders", src: "" },
      ]},
      { name: "Chapter 3 - Cutting Wasted Work", subchapters: [
        { name: "3.1 - Moving State Down and Lifting Content Up", src: "" },
        { name: "3.2 - Memoization and Computed State", src: "" },
        { name: "3.3 - When useMemo Costs More Than It Saves", src: "" },
      ]},
      { name: "Chapter 4 - Stable References", subchapters: [
        { name: "4.1 - React.memo and useCallback", src: "" },
        { name: "4.2 - Inline Objects and Functions That Break memo", src: "" },
        { name: "4.3 - Splitting Context to Stop Re-render Storms", src: "" },
      ]},
      { name: "Chapter 5 - Rendering Less", subchapters: [
        { name: "5.1 - Virtualizing the 5,000-Row Table", src: "" },
        { name: "5.2 - useTransition and useDeferredValue for Lag-Free Filtering", src: "" },
      ]},
      { name: "Chapter 6 - Finale", subchapters: [
        { name: "6.1 - Before and After: Profiling the Fixed Dashboard", src: "" },
        { name: "6.2 - Where from Here?", src: "" },
      ]},
    ],
    modules: [
      { title: "Render Fundamentals", description: "What actually triggers a re-render, render vs commit, and the shallow-equality checks React runs on every update." },
      { title: "Profiling First", description: "Use the React DevTools Profiler to find the components that render for nothing before you change a line." },
      { title: "Memoization & Computed State", description: "Restructure state first, then recompute derived data with useMemo only when its dependencies change." },
      { title: "React.memo & useCallback", description: "Skip re-renders by keeping props referentially stable, and dodge the inline-object and context traps that defeat memo." },
      { title: "Rendering Less", description: "Virtualize long lists and lean on useTransition so the dashboard stays responsive under real data." },
    ],
    learnings: ["What triggers a re-render", "Shallow equality and reference traps", "Profiling with React DevTools", "When React.memo actually helps", "useCallback vs useMemo", "List virtualization and useTransition"],
  },
];

export default tracks;

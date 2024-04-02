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
}

const tracks: Track[] = [
  {
    id: 1,
    title: "Build a Programming Language",
    priceINR: "179900",
    priceELSE: "2500",
    description: "Dive into the genesis of syntax with 'Building a Programming Language'. This isn't about tweaking what's already there; it's about architecting something groundbreaking. Unearth the foundational elements of language design—parsing, compiling, and interpreting. We'll navigate through abstract syntax trees, tokenization, and grammars, turning them into tools you wield with precision",
    trailer: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/Website%20utils%2Ftrail.mp4?alt=media&token=b7256e18-ce75-4272-ad6b-103770c02645",
    image: "https://res.cloudinary.com/practicaldev/image/fetch/s--e_rqeB7o--/c_limit%2Cf_auto%2Cfl_progressive%2Cq_auto%2Cw_880/https://cdn-images-1.medium.com/max/2400/1%2AFPtQLT2Zk-baHficCz_mXQ.png",
    theme: "text-green-500",
    theme2: "bg-green-700 hover:bg-green-500",
    border: "border-green-500",
    launched: false,
    courseContent: [
      { name: "Chapter 1 - Introduction", subchapters: [{ name: "1.1 - Language History", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F2.1%20-%20What%20are%20libraries.mp4?alt=media&token=437821cf-4512-4f9d-935d-8015ba81849b" }] },
      { name: "Chapter 2 - Human Languages", subchapters: [{ name: "2.1 - Libraries: First Principles", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F2.1%20-%20What%20are%20libraries.mp4?alt=media&token=437821cf-4512-4f9d-935d-8015ba81849b" }] },
      { name: "Chapter 3 - Is Programming Language a Syntax?", subchapters: [{ name: "2.1 - Libraries: First Principles", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F2.1%20-%20What%20are%20libraries.mp4?alt=media&token=437821cf-4512-4f9d-935d-8015ba81849b" }] },
      { name: "Chapter 4 - Language Components", subchapters: [{ name: "2.1 - Libraries: First Principles", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F2.1%20-%20What%20are%20libraries.mp4?alt=media&token=437821cf-4512-4f9d-935d-8015ba81849b" }] },
      { name: "Chapter 5 - Language Processors", subchapters: [{ name: "2.1 - Libraries: First Principles", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F2.1%20-%20What%20are%20libraries.mp4?alt=media&token=437821cf-4512-4f9d-935d-8015ba81849b" }] },
      { name: "Chapter 6 - Compilers vs Interpreters vs Transpilers", subchapters: [{ name: "2.1 - Libraries: First Principles", src: "https://firebasestorage.googleapis.com/v0/b/topdev-93530.appspot.com/o/CustomLibrary%2F2.1%20-%20What%20are%20libraries.mp4?alt=media&token=437821cf-4512-4f9d-935d-8015ba81849b" }] },
    ],
    modules: [
      { id: 1, title: "First Principles: Human Language", description: "Discover the art of crafting a library that's as plug-and-play as it gets." },
      { id: 2, title: "C++, Java Language Designs", description: "Uncover the architectural marvels of JavaScript's initial release." },
      { id: 3, title: "Machine Code, Bytecode, Your code.", description: "Inject your genius into JS's prototype." },
      { id: 4, title: "Javascript Architecture", description: "Craft functions like mask, shorten, highlight." },
      { id: 5, title: "Compiler, Interpretor & Transpiler", description: "Navigate the tricky waters of window pollution." },
      { id: 6, title: "Design a Language Grammer", description: "Tackle the client-side marvel with Window." },
      { id: 7, title: "Lexical Analysis", description: "Tackle the client-side marvel with Window." },
      { id: 8, title: "Build Abstract Syntax Tree", description: "Tackle the client-side marvel with Window." },
      { id: 9, title: "Interpret a Language AST", description: "Tackle the client-side marvel with Window." },
    ],
    learnings: [
      "How C++, Java, Python and JavaScript work",
      "AOT vs JIT Compilation",
      "The importance of Bytecode",
      "How to Design a Language Grammer",
      "The V8 engine",
      "Tokenization of Sourcecode",
      "Parsing Sourcecode to Create Abstract Syntax Tree",
      "Difference between Compiler & Interpreter",
      "How Interpreter works and create one",
      "How languages implement variable scoping",
      "Building a memory management system",
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
  },
  {
    id: 4,
    priceINR: "179900",
    priceELSE: "2500",
    title: "Product Engineering Essentials",
    theme: "text-orange-500",
    theme2: "bg-orange-700 hover:bg-orange-500",
    border: "border-orange-500",
    description: "This is a 0.1% DEV track.",
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
      { title: "Language Fundamentals Mastery", description: "Deepen your understanding of JavaScript's core concepts." },
      { title: "Asynchronous Programming Paradigms", description: "Explore the world of asynchronous JavaScript." },
      { title: "Functional Programming Techniques", description: "Elevate your coding skills by embracing functional programming principles." },
    ],
    learnings: ["Architecture of JavaScript as Waves in water", "The Js 1.0", "The OG module pattern : IIFE", "Hacking [[PROTOTYPE]]"],
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
    learnings: ["JavaScript Proxy — the engine behind reactivity", "Dependency tracking with WeakMap", "Observer pattern from scratch", "Batching and scheduling updates", "Memoized computed properties"],
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
];

export default tracks;
